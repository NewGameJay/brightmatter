const express = require('express');
const router = express.Router();
const { verifyApiKey } = require('../middleware/auth');
const { Kafka } = require('kafkajs');
const { v4: uuidv4 } = require('uuid');

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

const producer = kafka.producer();

// Create a new quest
router.post('/', verifyApiKey, async (req, res) => {
  try {
    // Generate a unique ID for the quest
    const questId = uuidv4();

    // Create quest event with required fields
    const questEvent = {
      id: questId,
      gameId: req.body.gameId,
      name: req.body.name,
      description: req.body.description,
      objectives: req.body.objectives,
      startDate: req.body.startDate,
      endDate: req.body.endDate,
      requirements: req.body.requirements,
      rewards: req.body.rewards,
      createdAt: new Date().toISOString()
    };

    // Validate required fields
    if (!questEvent.gameId || !questEvent.name || !questEvent.description || !questEvent.objectives) {
      return res.status(400).json({
        error: 'Missing required fields: gameId, name, description, and objectives are required'
      });
    }

    // Connect to Redpanda if not connected
    if (!producer.isConnected()) {
      await producer.connect();
    }

    // Send quest creation event to Redpanda
    await producer.send({
      topic: 'quest.events',
      messages: [
        {
          key: questId,
          value: JSON.stringify(questEvent)
        }
      ]
    });

    // Return success response with quest ID
    res.json({
      id: questId,
      status: 'processing',
      message: 'Quest creation event sent successfully'
    });
  } catch (error) {
    console.error('Error creating quest:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
