import { Handler } from '@netlify/functions';
import * as admin from 'firebase-admin';
import { Kafka } from 'kafkajs';
import { v4 as uuidv4 } from 'uuid';

// Initialize Firebase Admin
let app: admin.app.App;
try {
  app = admin.app();
} catch {
  app = admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
    })
  });
}

// Initialize Redpanda client
const kafka = new Kafka({
  brokers: (process.env.REDPANDA_BROKERS || '').split(','),
  clientId: process.env.REDPANDA_CLIENT_ID || 'brightmatter',
  sasl: process.env.REDPANDA_USERNAME && process.env.REDPANDA_PASSWORD ? {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD
  } : undefined,
  ssl: true
});

const producer = kafka.producer();

export const handler: Handler = async (event) => {
  // Only allow POST requests
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  try {
    // Parse request body
    const body = JSON.parse(event.body || '{}');
    const apiKey = event.headers['x-api-key'];

    // Validate API key
    if (!apiKey) {
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'API key required' })
      };
    }

    // Validate required fields
    if (!body.gameId || !body.type || !body.data) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Missing required fields' })
      };
    }

    // Verify API key and game ID using Firebase
    const studio = await admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .where('gameId', '==', body.gameId)
      .limit(1)
      .get();

    if (studio.empty) {
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'Invalid API key or game ID' })
      };
    }

    // Generate event ID
    const eventId = uuidv4();

    // Transform event for BrightMatter format
    const brightMatterEvent = {
      id: eventId,
      gameId: body.gameId,
      studioId: studio.docs[0].id,
      type: body.type,
      playerId: body.data.playerId || 'anonymous',
      playerName: body.data.playerName || 'Anonymous Player',
      timestamp: new Date().toISOString(),
      metadata: {
        ...body.data,
        platform: body.data.platform || 'unknown',
        sdkVersion: body.data.sdkVersion || '1.0.0',
        apiVersion: 'v1'
      }
    };

    // Connect to Redpanda
    await producer.connect();

    // Send event to Redpanda
    await producer.send({
      topic: 'game-events',
      messages: [{
        key: body.gameId,
        value: JSON.stringify(brightMatterEvent)
      }]
    });

    // Disconnect from Redpanda
    await producer.disconnect();

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        event: {
          id: eventId,
          type: body.type,
          gameId: body.gameId
        }
      })
    };
  } catch (error) {
    console.error('Error processing event:', error);
    console.error('Error details:', {
      brokers: process.env.REDPANDA_BROKERS,
      username: process.env.REDPANDA_USERNAME ? 'set' : 'not set',
      password: process.env.REDPANDA_PASSWORD ? 'set' : 'not set',
      firebase: {
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL ? 'set' : 'not set',
        privateKey: process.env.FIREBASE_PRIVATE_KEY ? 'set' : 'not set'
      }
    });
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: error instanceof Error ? error.message : 'Failed to process event'
      })
    };
  }
};
