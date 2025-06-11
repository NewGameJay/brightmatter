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
  host: 'brightmatter-db.cwra0uc6su8r.us-east-1.rds.amazonaws.com',
  port: 5432,
  database: 'brightmatter',
  user: 'postgres',
  password: '2gL~5$_i-evP2!03w(7dUAU.]Miz',
  ssl: {
    rejectUnauthorized: false
  }
});

// Validate environment variables
if (!process.env.REDPANDA_CLIENT_ID || !process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

if (!process.env.POSTGRES_HOST || !process.env.POSTGRES_DB || !process.env.POSTGRES_USER || !process.env.POSTGRES_PASSWORD) {
  console.error('Missing required PostgreSQL environment variables');
  process.exit(1);
}

// Validate Redpanda environment variables
if (!process.env.REDPANDA_CLIENT_ID || !process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

// Initialize Kafka client
const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID!,
  brokers: [process.env.REDPANDA_BROKERS!],
  ssl: true,
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME!,
    password: process.env.REDPANDA_PASSWORD!
  }
});

const consumer = kafka.consumer({ groupId: 'event-processor-group' });

async function processEvent(event: any) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Insert into game_events table
    const query = `
      INSERT INTO game_events (
        user_id,
        game_id,
        event_type,
        payload,
        timestamp
      ) VALUES ($1, $2, $3, $4, $5)
      RETURNING event_id
    `;

    const values = [
      event.user_id,
      event.game_id,
      event.event_type,
      event.payload,
      event.timestamp
    ];

    const result = await client.query(query, values);
    console.log('Event stored in PostgreSQL:', result.rows[0].event_id);

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

    await consumer.subscribe({
      topic: 'game.events.raw',
      fromBeginning: true
    });

    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          const event = JSON.parse(message.value?.toString() || '');
          console.log('Processing event:', event);
          await processEvent(event);
        } catch (error) {
          console.error('Error processing message:', error);
        }
      }
    });

    console.log('Event processor started');
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
