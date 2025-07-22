const { Pool } = require('pg');
const { Kafka } = require('kafkajs');
require('dotenv').config();

// Validate environment variables
if (!process.env.POSTGRES_HOST || !process.env.POSTGRES_DB || !process.env.POSTGRES_USER || !process.env.POSTGRES_PASSWORD) {
  console.error('Missing required PostgreSQL environment variables');
  process.exit(1);
}

if (!process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

// Initialize PostgreSQL client
const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: parseInt(process.env.POSTGRES_PORT) || 5432,
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  ssl: {
    rejectUnauthorized: false
  }
});

// Initialize Kafka client
const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID || 'brightmatter',
  brokers: [process.env.REDPANDA_BROKERS],
  ssl: {
    rejectUnauthorized: false
  },
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD
  }
});

// Process game events
async function processGameEvent(event) {
  const { user_id, game_id, event_type, payload, timestamp } = event;
  
  try {
    await pool.query(
      `INSERT INTO game_events (user_id, game_id, event_type, payload, timestamp)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING event_id`,
      [user_id, game_id, event_type, payload, new Date(timestamp)]
    );
    console.log(`Processed game event: ${event_type} for user ${user_id}`);
  } catch (error) {
    console.error('Error processing game event:', error);
    throw error;
  }
}



// Start the consumer
async function startConsumer() {
  try {
    console.log('Connecting to PostgreSQL...');
    await pool.connect();
    console.log('✅ Connected to PostgreSQL');

    console.log('Connecting to Redpanda...');
    const consumer = kafka.consumer({ groupId: 'event-processor-group' });
    await consumer.connect();
    console.log('✅ Connected to Redpanda cluster');

    // Subscribe to topics
    await consumer.subscribe({
      topics: ['game.events'],
      fromBeginning: true
    });
    console.log('Successfully subscribed to game.events topic');

    // Start consuming messages
    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          const event = JSON.parse(message.value.toString());
          console.log(`Received ${topic} event:`, {
            partition,
            offset: message.offset,
            value: message.value?.toString()
          });

          if (topic === 'game.events') {
            await processGameEvent(event);
          }
        } catch (error) {
          console.error(`Error processing message from topic ${topic}:`, error);
          console.error('Message was:', message.value?.toString());
        }
      }
    });

  } catch (error) {
    console.error('Error starting consumer:', error);
    process.exit(1);
  }
}

// Handle graceful shutdown
const shutdown = async () => {
  try {
    console.log('Shutting down event processor...');
    await pool.end();
    console.log('PostgreSQL connection closed');
    process.exit(0);
  } catch (error) {
    console.error('Error during shutdown:', error);
    process.exit(1);
  }
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

console.log('Event processor started...');
startConsumer();

