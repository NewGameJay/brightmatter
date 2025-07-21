import { Handler } from '@netlify/functions';
import { Kafka } from 'kafkajs';
import * as admin from 'firebase-admin';
import { v4 as uuidv4 } from 'uuid';

// Initialize Firebase Admin
let app: admin.app.App;
try {
  if (!admin.apps.length) {
    admin.initializeApp({
      credential: admin.credential.cert({
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
        privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
      })
    });
  }
} catch {
  admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
    })
  });
}



// Initialize Redpanda client
const kafka = new Kafka({
  brokers: [process.env.REDPANDA_BROKERS || ''],
  clientId: process.env.REDPANDA_CLIENT_ID,
  ssl: true,
  sasl: process.env.REDPANDA_USERNAME && process.env.REDPANDA_PASSWORD ? {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD
  } : undefined
});

// Configure producer with auto topic creation
const producer = kafka.producer();

// Add error handler to producer
producer.on('producer.connect', () => {
  console.log('Producer connected to Redpanda');
});

producer.on('producer.disconnect', () => {
  console.log('Producer disconnected from Redpanda');
});

producer.on('producer.network.request_timeout', (error) => {
  console.error('Producer network timeout:', error);
});

export const handler: Handler = async (event, context) => {
  // Handle CORS
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 204,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
      },
      body: ''
    };
  }

  // Route request based on path
  const path = event.path.replace(/\.netlify\/functions\/[^/]+/, '');
  if (path.startsWith('/events')) {
    return handleGameEvent(event);
  } else {
    return {
      statusCode: 404,
      body: JSON.stringify({ error: 'Not found' })
    };
  }
};

// Handle game events
const handleGameEvent = async (event: any) => {
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
    console.log('Starting Firebase authentication for game event...');
    console.log('API Key:', apiKey ? 'provided' : 'missing');
    console.log('Game ID:', body.gameId);
    console.log('Firebase config:', {
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL ? 'set' : 'not set',
      privateKey: process.env.FIREBASE_PRIVATE_KEY ? 'set' : 'not set'
    });

    const studioQuery = admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .where('gameId', '==', body.gameId)
      .limit(1);

    console.log('Executing Firebase query for game event...');
    const studio = await studioQuery.get();
    console.log('Firebase query complete. Empty?', studio.empty);

    if (studio.empty) {
      console.log('No studio found with provided API key and game ID');
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'Invalid API key or game ID' })
      };
    }
    
    console.log('Studio found, proceeding with game event');

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

    console.log('Connecting to Redpanda with config:', {
      brokers: process.env.REDPANDA_BROKERS,
      clientId: process.env.REDPANDA_CLIENT_ID,
      username: process.env.REDPANDA_USERNAME ? 'set' : 'not set',
      password: process.env.REDPANDA_PASSWORD ? 'set' : 'not set'
    });

    // Connect to Redpanda
    await producer.connect();
    console.log('Connected to Redpanda');

    // Send event to Redpanda
    console.log('Sending event to topic: game.events.raw');
    await producer.send({
      topic: 'game.events.raw',
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
