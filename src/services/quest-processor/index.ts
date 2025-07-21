import { Pool } from 'pg';
import { Kafka } from 'kafkajs';
import dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../.env') });

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
  }
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

const consumer = kafka.consumer({ groupId: 'quest-processor-group' });

interface QuestEvent {
  id: string;
  gameId: string;
  name: string;
  description: string;
  objectives: any[];
  startDate?: string;
  endDate?: string;
  requirements?: any;
  rewards?: any;
  createdAt: string;
}

async function processQuestEvent(event: QuestEvent) {
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
        rewards,
        start_date,
        end_date,
        requirements,
        created_at,
        updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
      ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        objectives = EXCLUDED.objectives,
        rewards = EXCLUDED.rewards,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        requirements = EXCLUDED.requirements,
        updated_at = EXCLUDED.updated_at
    `;

    const values = [
      event.id,
      event.gameId,
      event.name,
      event.description,
      JSON.stringify(event.objectives),
      JSON.stringify(event.rewards || {}),
      event.startDate,
      event.endDate,
      JSON.stringify(event.requirements || {}),
      event.createdAt
    ];

    await client.query(query, values);
    console.log('Quest stored in PostgreSQL:', event.id);

    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function startConsumer() {
  try {
    await consumer.connect();
    console.log('Connected to Redpanda');

    // Subscribe to quest events
    await consumer.subscribe({ topic: 'quest.events', fromBeginning: true });
    console.log('Subscribed to quest events');

    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          const event = JSON.parse(message.value?.toString() || '');
          console.log('Processing quest event:', event);
          await processQuestEvent(event);
        } catch (error) {
          console.error('Error processing message:', error);
        }
      }
    });

    console.log('Quest processor started');
  } catch (error) {
    console.error('Error starting consumer:', error);
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
