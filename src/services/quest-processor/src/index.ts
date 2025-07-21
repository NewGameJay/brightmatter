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

const consumer = kafka.consumer({ groupId: 'social-auth-processor-group' });

interface QuestEvent {
  id: string;
  gameId: string;
  name: string;
  description: string;
  objectives: Array<{
    id: string;
    description: string;
    requiredProgress: number;
    reward?: {
      type: string;
      amount: number;
    };
  }>;
  startDate: string;
  endDate?: string;
  requirements?: {
    level?: number;
    items?: string[];
    quests?: string[];
  };
  rewards: Array<{
    type: string;
    amount: number;
    itemId?: string;
  }>;
  createdAt: string;
}

async function processQuestEvent(event: QuestEvent) {
  console.log('Processing quest event:', {
    id: event.id,
    gameId: event.gameId,
    name: event.name
  });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Insert into quests table
    const query = `
      INSERT INTO quests (
        id,
        game_id,
        name,
        description,
        objectives,
        start_date,
        end_date,
        requirements,
        rewards,
        created_at,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
      ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        objectives = EXCLUDED.objectives,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        requirements = EXCLUDED.requirements,
        rewards = EXCLUDED.rewards,
        updated_at = EXCLUDED.updated_at
    `;

    const values = [
      event.id,
      event.gameId,
      event.name,
      event.description,
      JSON.stringify(event.objectives),
      event.startDate,
      event.endDate,
      JSON.stringify(event.requirements),
      JSON.stringify(event.rewards),
      new Date().toISOString()
    ];

    console.log('Executing quest insert/update query...');
    await client.query(query, values);
    console.log('Quest stored in PostgreSQL:', event.id);

    await client.query('COMMIT');
  } catch (error) {
    console.error('Error processing quest event:', error);
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function startConsumer() {
  try {
    console.log('Starting quest consumer...');
    await consumer.connect();
    console.log('Connected to Redpanda');

    console.log('Subscribing to quest.events topic...');
    await consumer.subscribe({
      topic: 'quest.events',
      fromBeginning: true
    });
    console.log('Successfully subscribed to quest.events topic');

    // Add HTTP server for health checks (required for Replit deployment)
    import http from 'http';

    const server = http.createServer((req, res) => {
      if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'healthy', service: 'quest-processor' }));
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    server.listen(8080, '0.0.0.0', () => {
      console.log('Health check server running on port 8080');
    });

    console.log('Starting message processing loop...');
    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          console.log('Received message:', {
            topic,
            partition,
            offset: message.offset,
            timestamp: message.timestamp
          });

          const event = JSON.parse(message.value?.toString() || '');
          console.log('Parsed quest event:', {
            id: event.id,
            gameId: event.gameId,
            name: event.name,
            type: event.type
          });

          await processQuestEvent(event);
          console.log('Successfully processed quest event:', event.id);
        } catch (error) {
          console.error('Error processing quest message:', error);
          console.error('Message details:', {
            topic,
            partition,
            offset: message.offset,
            key: message.key?.toString(),
            value: message.value?.toString()
          });
        }
      }
    });

    console.log('Quest Processor started. Listening for events...');

    // Keep the process running
    process.stdin.resume();
  } catch (error: unknown) {
    if (error instanceof Error) {
      console.error('Error starting quest consumer:', error.message);
      console.error('Stack trace:', error.stack);
    } else {
      console.error('Unknown error starting quest consumer:', error);
    }
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