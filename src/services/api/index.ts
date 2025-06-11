import express from 'express';
import bodyParser from 'body-parser';
import admin from 'firebase-admin';
import dotenv from 'dotenv';
import path from 'path';
import { Kafka } from 'kafkajs';
import { FirebaseEvent, GameEvent } from './types';
import { transformFirebaseEvent, validateEventType } from './transforms';

// Load environment variables from root .env
dotenv.config({ path: path.join(__dirname, '../../../.env') });

// Initialize Firebase Admin
if (!process.env.FIREBASE_PROJECT_ID || !process.env.FIREBASE_CLIENT_EMAIL || !process.env.FIREBASE_PRIVATE_KEY) {
  throw new Error('Missing Firebase credentials in environment variables');
}

try {
  // Check if app is already initialized
  if (!admin.apps.length) {
    admin.initializeApp({
      credential: admin.credential.cert({
        projectId: process.env.FIREBASE_PROJECT_ID,
        clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
        privateKey: process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n')
      })
    });

    // Configure Firestore settings
    const db = admin.firestore();
    db.settings({
      ignoreUndefinedProperties: true
    });
    console.log('Firebase Admin initialized successfully');
  }
} catch (error) {
  console.error('Error initializing Firebase Admin:', error);
  process.exit(1);
}

const app = express();
app.use(bodyParser.json());

// Add request logging
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.url}`);
  next();
});

// Validate game credentials against Firebase
async function validateGameCredentials(gameId: string, studioId: string, apiKey: string): Promise<boolean> {
  console.log('Validating credentials for:', { gameId, studioId });
  try {
    const gameDoc = await admin.firestore()
      .collection('games')
      .doc(gameId)
      .get();

    if (!gameDoc.exists) {
      console.log('Game not found:', gameId);
      return false;
    }

    const gameData = gameDoc.data();
    console.log('Game data:', gameData);

    if (gameData?.studioId !== studioId) {
      console.log('Studio ID mismatch. Expected:', gameData?.studioId, 'Got:', studioId);
      return false;
    }

    if (gameData?.apiKey !== apiKey) {
      console.log('API key mismatch. Expected:', gameData?.apiKey, 'Got:', apiKey);
      return false;
    }

    console.log('Credentials validated successfully');
    return true;
  } catch (error) {
    console.error('Error validating game credentials:', error);
    return false;
  }
}

// Event validation middleware
const validateEvent = async (req: express.Request, res: express.Response, next: express.NextFunction) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.set({
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, x-api-key',
      'Access-Control-Max-Age': '86400',
    }).sendStatus(204);
    return;
  }

  // Get API key from headers
  const apiKey = req.headers['x-api-key'] as string;
  if (!apiKey) {
    return res.status(401).json({ error: 'Missing API key' });
  }

  const event = req.body;

  // Validate required fields
  if (!event.gameId || !event.type || !event.data) {
    return res.status(400).json({ 
      error: 'Missing required fields',
      required: ['gameId', 'type', 'data']
    });
  }

  // Validate event type
  if (!validateEventType(event.type)) {
    return res.status(400).json({ 
      error: 'Invalid event type',
      valid_types: ['leaderboard_update', 'game_start', 'game_end', 'achievement', 
                   'score_update', 'kill', 'death', 'level_up', 'quest_progress', 
                   'item_acquire', 'custom']
    });
  }

  try {
    // Find studio by API key
    const studioSnapshot = await admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .get();

    if (studioSnapshot.empty) {
      return res.status(401).json({ error: 'Invalid API key' });
    }

    const studio = studioSnapshot.docs[0];
    const studioData = studio.data();

    // Verify game ID belongs to this studio
    if (studioData.gameId !== event.gameId) {
      return res.status(403).json({ error: 'Game ID does not match studio' });
    }

    // Add studio ID to request for downstream processing
    req.body.studioId = studio.id;
    next();
  } catch (error) {
    console.error('Error validating credentials:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
};

// Start the server
// Validate Redpanda environment variables
if (!process.env.REDPANDA_CLIENT_ID || !process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

const startServer = async () => {
  // Connect to Redpanda
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
  const producer = kafka.producer();

  try {
    await producer.connect();
    console.log('Connected to Redpanda');
  } catch (error) {
    console.error('Failed to connect to Redpanda:', error);
    process.exit(1);
  }

  // TODO: Re-enable Redpanda after fixing auth
  // POST /events endpoint
  app.post('/events', validateEvent, async (req: express.Request, res: express.Response) => {
    console.log('Received event:', JSON.stringify(req.body, null, 2));
    try {
      // Transform BoredGamer event format to BrightMatter format
      const boredGamerEvent = req.body;
      const brightMatterEvent: FirebaseEvent = {
        gameId: boredGamerEvent.gameId,
        studioId: boredGamerEvent.studioId, // Added by validateEvent middleware
        type: boredGamerEvent.type,
        playerId: boredGamerEvent.data.playerId || 'anonymous',
        playerName: boredGamerEvent.data.playerName || 'Anonymous Player',
        timestamp: new Date().toISOString(),
        metadata: {
          ...boredGamerEvent.data,
          platform: boredGamerEvent.data.platform || 'unknown',
          sdkVersion: boredGamerEvent.data.sdkVersion || '1.0.0',
          apiVersion: 'v1'
        }
      };

      // Transform to game event format
      const gameEvent = transformFirebaseEvent(brightMatterEvent);

      // Prepare event document
      console.log('Transformed event:', JSON.stringify(gameEvent, null, 2));
      
      const eventDoc = {
        ...gameEvent,
        timestamp: new Date(),
        received_at: new Date(),
        source_ip: req.ip
      };

      console.log('Publishing event:', JSON.stringify(eventDoc, null, 2));
      
      // Publish to Redpanda
      try {
        await producer.send({
          topic: 'game.events.raw',
          messages: [{
            key: eventDoc.game_id,
            value: JSON.stringify(eventDoc)
          }]
        });
        console.log('Event published to Redpanda');
      } catch (error) {
        console.error('Failed to publish to Redpanda:', error);
        throw error;
      }

      // Generate a unique event ID for response
      const eventId = `${eventDoc.game_id}_${Date.now()}`;

      // Return response in BoredGamer format
      res.status(200).json({ 
        success: true, 
        event: {
          type: boredGamerEvent.type,
          gameId: boredGamerEvent.gameId,
          id: eventId
        }
      });
    } catch (error) {
      const err = error as Error;
      console.error('Error processing event:', err);
      console.error('Stack:', err.stack);
      res.status(500).json({ 
        error: 'Failed to process event',
        message: err.message,
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      });
    }
  });

  // Health check endpoint
  app.get('/health', (req, res) => {
    res.status(200).json({ status: 'healthy' });
  });

  const PORT = process.env.PORT || 3001;
  const server = app.listen(PORT, () => {
    console.log(`Event API listening on port ${PORT}`);
  });

  server.on('error', (error: any) => {
    console.error('Server error:', error);
    process.exit(1);
  });

  process.on('SIGTERM', async () => {
    console.log('SIGTERM received, shutting down...');
    try {
      await producer.disconnect();
      console.log('Disconnected from Redpanda');
    } catch (error) {
      console.error('Error disconnecting from Redpanda:', error);
    }
    process.exit(0);
  });

  process.on('uncaughtException', (error) => {
    console.error('Uncaught exception:', error);
    process.exit(1);
  });

  process.on('unhandledRejection', (error) => {
    console.error('Unhandled rejection:', error);
    process.exit(1);
  });
};

startServer();
