const { Kafka } = require('kafkajs');
require('dotenv').config();

const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID,
  brokers: process.env.REDPANDA_BROKERS.split(','),
  ssl: true,
  sasl: {
    mechanism: 'SCRAM-SHA-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD,
  },
});

const producer = kafka.producer();
const consumer = kafka.consumer({ groupId: 'social-auth-processor-group' });

module.exports = {
  kafka,
  producer,
  consumer,
};
