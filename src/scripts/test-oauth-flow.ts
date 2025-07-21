import { Kafka, SASLOptions } from 'kafkajs';
import dotenv from 'dotenv';

dotenv.config();

if (!process.env.REDPANDA_BROKERS) {
  throw new Error('REDPANDA_BROKERS environment variable is required');
}

const kafka = new Kafka({
  clientId: 'oauth-test-consumer',
  brokers: process.env.REDPANDA_BROKERS.split(','),
  ssl: true,
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME || '',
    password: process.env.REDPANDA_PASSWORD || '',
  } as SASLOptions,
});

const consumer = kafka.consumer({ groupId: 'oauth-test-group' });
const producer = kafka.producer();

async function testOAuthFlow() {
  await consumer.connect();
  await producer.connect();

  // Subscribe to all OAuth-related topics
  await consumer.subscribe({ 
    topics: [
      'social.connect',
      'social.connect.callback',
      'social.auth.url',
      'social.auth.completed'
    ] 
  });

  // Start listening for messages
  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
      console.log('Received message on topic:', topic);
      console.log('Message:', {
        value: message.value?.toString(),
        headers: message.headers,
        key: message.key?.toString(),
      });
    },
  });

  // Send a test OAuth initiation event
  const testUserId = 'test-user-123';
  await producer.send({
    topic: 'social.connect',
    messages: [{
      key: testUserId,
      value: JSON.stringify({
        userId: testUserId,
        platform: 'twitter',
        timestamp: Date.now()
      })
    }]
  });

  console.log('Test OAuth initiation event sent');
  console.log('Listening for events... Press Ctrl+C to exit');
}

// Handle graceful shutdown
const errorTypes = ['unhandledRejection', 'uncaughtException'];
const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

errorTypes.forEach(type => {
  process.on(type, async () => {
    try {
      console.log(`process.on ${type}`);
      await consumer.disconnect();
      await producer.disconnect();
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
    } finally {
      process.kill(process.pid, type);
    }
  });
});

testOAuthFlow().catch(console.error);
