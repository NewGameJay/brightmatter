import { Kafka, SASLOptions } from 'kafkajs';
import { TwitterApi } from 'twitter-api-v2';
import { Pool } from 'pg';
import dotenv from 'dotenv';

dotenv.config();

// Initialize PostgreSQL client
const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: parseInt(process.env.POSTGRES_PORT || '5432'),
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  ssl: {
    rejectUnauthorized: false
  },
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 10000,
  max: 20
});

// Add error handler to the pool
pool.on('error', (err) => {
  console.error('Unexpected error on idle PostgreSQL client', err);
});

// Initialize Kafka client
const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID,
  brokers: (process.env.REDPANDA_BROKERS || '').split(','),
  ssl: {
    rejectUnauthorized: false // Trust Redpanda Cloud certificates
  },
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME || '',
    password: process.env.REDPANDA_PASSWORD || '',
  } as SASLOptions,
});

const consumer = kafka.consumer({ groupId: 'social-auth-processor-group' });
const producer = kafka.producer();

// Initialize Twitter OAuth 2.0 client
const twitterClient = new TwitterApi({
  clientId: process.env.TWITTER_CLIENT_ID || '',
  clientSecret: process.env.TWITTER_CLIENT_SECRET || '',
});

async function handleOAuthInitiation(payload: any) {
  try {
    const { userId } = payload;
    
    console.log('Generating OAuth URL for user:', userId);

    // Generate OAuth URL with state
    const { url, codeVerifier, state } = await twitterClient.generateOAuth2AuthLink(
      process.env.TWITTER_CALLBACK_URL || 'https://api.brightmatter.io/auth/twitter/callback',
      { scope: ['tweet.read', 'users.read', 'offline.access'] }
    );

    // Emit oauth.url.generated event
    await producer.send({
      topic: 'social.connect',
      messages: [{
        key: userId,
        value: JSON.stringify({
          userId,
          authUrl: url,
          state
        })
      }]
    });

    console.log(`OAuth URL generated for user ${userId}`);

  } catch (error) {
    console.error('Test: Failed to send to Redpanda:', error);
    // Emit failure event
    await producer.send({
      topic: 'social.auth.error',
      messages: [{
        key: payload.userId || 'unknown',
        value: JSON.stringify({
          error: 'Test failed',
          details: error instanceof Error ? error.message : 'Unknown error'
        })
      }]
    });
  }
}

async function handleOAuthCallback(payload: any) {
  const client = await pool.connect();
  try {
    const { userId, code, state } = payload;
    console.log('Processing OAuth callback for user:', userId);

    // Exchange code for tokens
    const { accessToken, refreshToken, expiresIn } = await twitterClient.loginWithOAuth2({
      code,
      codeVerifier: state, // We stored this in state during initiation
      redirectUri: process.env.TWITTER_CALLBACK_URL || 'https://api.brightmatter.io/auth/twitter/callback'
    });

    // Get user info from Twitter
    const twitterApiClient = new TwitterApi(accessToken);
    const user = await twitterApiClient.v2.me();

    // Begin transaction
    await client.query('BEGIN');

    // Store tokens in social_accounts table with all fields
    const query = `
      INSERT INTO social_accounts (
        user_id,
        platform,
        external_user_id,
        username,
        access_token,
        refresh_token,
        token_expires_at,
        scopes,
        metadata,
        created_at,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
      ON CONFLICT (user_id, platform) DO UPDATE SET
        external_user_id = EXCLUDED.external_user_id,
        username = EXCLUDED.username,
        access_token = EXCLUDED.access_token,
        refresh_token = EXCLUDED.refresh_token,
        token_expires_at = EXCLUDED.token_expires_at,
        scopes = EXCLUDED.scopes,
        metadata = social_accounts.metadata || EXCLUDED.metadata,
        updated_at = NOW()
    `;

    // Get user's public metrics
    const userWithMetrics = await twitterApiClient.v2.user(user.data.id, {
      'user.fields': ['public_metrics', 'description', 'created_at']
    });

    const values = [
      userId,
      'twitter',
      user.data.id,
      user.data.username,
      accessToken,
      refreshToken,
      new Date(Date.now() + expiresIn * 1000),
      ['tweet.read', 'users.read', 'offline.access'],  // Granted scopes
      JSON.stringify({
        description: userWithMetrics.data.description,
        created_at: userWithMetrics.data.created_at,
        metrics: userWithMetrics.data.public_metrics,
        last_updated: new Date().toISOString()
      })
    ];

    await client.query(query, values);
    await client.query('COMMIT');

    // Emit success event
    await producer.send({
      topic: 'social.connect.callback',
      messages: [{
        key: userId,
        value: JSON.stringify({
          userId,
          platform: 'twitter',
          username: user.data.username,
          externalUserId: user.data.id,
          timestamp: Date.now()
        })
      }]
    });

    console.log('Successfully stored Twitter tokens for user:', userId);

  } catch (error) {
    console.error('OAuth callback failed:', error);
    await client.query('ROLLBACK');
    
    await producer.send({
      topic: 'social.auth.error',
      messages: [{
        key: payload.userId || 'unknown',
        value: JSON.stringify({
          error: 'OAuth callback failed',
          details: error instanceof Error ? error.message : 'Unknown error'
        })
      }]
    });
  } finally {
    client.release();
  }
}

// Start the consumer
async function startConsumer() {
  try {
    console.log('Test: Connecting to Redpanda...');
    await consumer.connect();
    await producer.connect();

    await consumer.subscribe({
      topics: ['social.connect', 'social.connect.callback']
    });

    console.log('OAuth processor started, listening for events...');

    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        const payload = JSON.parse(message.value?.toString() || '{}');
        console.log(`Received message on topic ${topic}:`, payload);

        // Parse event type from payload
        const { type, ...data } = payload;
        
        switch (type) {
          case 'CONNECT_TWITTER':
            await handleOAuthInitiation(data);
            break;
          case 'OAUTH_CALLBACK':
            await handleOAuthCallback(data);
            break;
          default:
            console.warn('Unknown event type:', type);
        }
      }
    });
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  }
}

// Handle graceful shutdown
const errorTypes = ['unhandledRejection', 'uncaughtException'];
const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

errorTypes.forEach(type => {
  process.on(type, async (error) => {
    try {
      console.log(`process.on ${type}`, error);
      await consumer.disconnect();
      await producer.disconnect();
      // Skip pool.end() for testing
      process.exit(0);
    } catch (_) {
      process.exit(1);
    }
  });
});

signalTraps.forEach(type => {
  process.once(type, async () => {
    try {
      await consumer.disconnect();
      await producer.disconnect();
      // Skip pool.end() for testing
    } finally {
      process.kill(process.pid, type);
    }
  });
});

// Start the service
startConsumer().catch(console.error);
