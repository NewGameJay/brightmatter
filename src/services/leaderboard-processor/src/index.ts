import { Pool } from 'pg';
import { Kafka } from 'kafkajs';
import dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../../.env') });

// Validate PostgreSQL environment variables
if (!process.env.POSTGRES_HOST || !process.env.POSTGRES_DB || !process.env.POSTGRES_USER || !process.env.POSTGRES_PASSWORD) {
  console.error('Missing required PostgreSQL environment variables');
  process.exit(1);
}

// Initialize PostgreSQL client
const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: parseInt(process.env.POSTGRES_PORT || '5432'),
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  ssl: {
    rejectUnauthorized: false // For development only
  },
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 10000,
  max: 20
});

// Add error handler to the pool
pool.on('error', (err) => {
  console.error('Unexpected error on idle PostgreSQL client', err);
});

// Validate Redpanda environment variables
if (!process.env.REDPANDA_CLIENT_ID || !process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

// Initialize Kafka client
const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID,
  brokers: [process.env.REDPANDA_BROKERS],
  ssl: true,
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD
  }
});

const consumer = kafka.consumer({ groupId: 'leaderboard-processor-group' });

interface LeaderboardEvent {
  id: string;
  gameId: string;
  name: string;
  eventType: string;
  scoreField: string;
  scoreType: 'highest' | 'lowest' | 'sum';
  timePeriod: 'daily' | 'weekly' | 'monthly' | 'all-time';
  startDate: string;
  endDate: string;
  isRolling: boolean;
  maxEntriesPerUser: number;
  highestScoresPerUser: number;
  requiredMetadata: string[];
  createdAt: string;
}

async function processLeaderboardEvent(event: LeaderboardEvent) {
  console.log('Processing leaderboard event:', {
    id: event.id,
    gameId: event.gameId,
    name: event.name,
    eventType: event.eventType
  });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Insert into leaderboards table
    const query = `
      INSERT INTO leaderboards (
        id,
        game_id,
        name,
        event_type,
        score_field,
        score_type,
        time_period,
        start_date,
        end_date,
        is_rolling,
        max_entries_per_user,
        highest_scores_per_user,
        required_metadata,
        created_at,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $14)
      ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        event_type = EXCLUDED.event_type,
        score_field = EXCLUDED.score_field,
        score_type = EXCLUDED.score_type,
        time_period = EXCLUDED.time_period,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        is_rolling = EXCLUDED.is_rolling,
        max_entries_per_user = EXCLUDED.max_entries_per_user,
        highest_scores_per_user = EXCLUDED.highest_scores_per_user,
        required_metadata = EXCLUDED.required_metadata,
        updated_at = EXCLUDED.updated_at
    `;

    const values = [
      event.id,
      event.gameId,
      event.name,
      event.eventType,
      event.scoreField,
      event.scoreType,
      event.timePeriod,
      event.startDate,
      event.endDate,
      event.isRolling,
      event.maxEntriesPerUser,
      event.highestScoresPerUser,
      event.requiredMetadata,
      new Date().toISOString()
    ];

    console.log('Executing leaderboard insert/update query...');
    await client.query(query, values);
    console.log('Leaderboard stored in PostgreSQL:', event.id);

    await client.query('COMMIT');
  } catch (error) {
    console.error('Error processing leaderboard event:', error);
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function startConsumer() {
  try {
    console.log('Starting leaderboard processor...');
    console.log('Connecting to Redpanda with config:', {
      clientId: process.env.REDPANDA_CLIENT_ID,
      brokers: [process.env.REDPANDA_BROKERS],
      ssl: true,
      sasl: {
        mechanism: 'scram-sha-256',
        username: process.env.REDPANDA_USERNAME ? 'set' : 'not set',
        password: process.env.REDPANDA_PASSWORD ? 'set' : 'not set'
      }
    });

    await consumer.connect();
    console.log('Successfully connected to Redpanda');

    await consumer.subscribe({
      topic: 'leaderboard.events',
      fromBeginning: true
    });
    console.log('Successfully subscribed to leaderboard.events topic');

    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          const event = JSON.parse(message.value?.toString() || '');
          console.log('Received leaderboard event:', {
            id: event.id,
            gameId: event.gameId,
            name: event.name
          });
          console.log('Event details:', event);
          await processLeaderboardEvent(event);
          console.log('Leaderboard event processed successfully:', event.id);
        } catch (error) {
          console.error('Error processing leaderboard message:', error);
        }
      }
    });

    console.log('Leaderboard processor started');
  } catch (error) {
    console.error('Error starting leaderboard consumer:', error);
    process.exit(1);
  }
}

// Handle graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down...');
  try {
    await consumer.disconnect();
    await pool.end();
    console.log('Disconnected from Redpanda and PostgreSQL');
  } catch (error) {
    console.error('Error during shutdown:', error);
  }
  process.exit(0);
});

// Start consumer and keep process running
startConsumer().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});

// Keep process running
process.stdin.resume();
