import { Kafka, SASLOptions } from 'kafkajs';
import dotenv from 'dotenv';

dotenv.config();

if (!process.env.REDPANDA_BROKERS) {
  throw new Error('REDPANDA_BROKERS environment variable is required');
}

const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID || 'brightmatter',
  brokers: process.env.REDPANDA_BROKERS.split(','),
  ssl: true,
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME || '',
    password: process.env.REDPANDA_PASSWORD || '',
  } as SASLOptions,
});

const admin = kafka.admin();

async function createTopics() {
  try {
    await admin.connect();
    
    const topics = [
      {
        topic: 'social.connect',
        numPartitions: 3,
        replicationFactor: 3
      },
      {
        topic: 'social.connect.callback',
        numPartitions: 3,
        replicationFactor: 3
      },
      {
        topic: 'social.auth.url',
        numPartitions: 3,
        replicationFactor: 3
      },
      {
        topic: 'social.auth.completed',
        numPartitions: 3,
        replicationFactor: 3
      }
    ];

    await admin.createTopics({
      topics,
      waitForLeaders: true
    });

    console.log('Topics created successfully');

    // List all topics to verify
    const existingTopics = await admin.listTopics();
    console.log('Existing topics:', existingTopics);

  } catch (error) {
    console.error('Error:', error);
  } finally {
    await admin.disconnect();
  }
}

createTopics().catch(console.error);
