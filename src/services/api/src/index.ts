import 'dotenv/config';
import express from 'express';
import bodyParser from 'body-parser';
import admin from 'firebase-admin';
import dotenv from 'dotenv';
import path from 'path';
import { Kafka } from 'kafkajs';
import { Pool } from 'pg';
import crypto from 'crypto';
import { FirebaseEvent, GameEvent } from './types';
import { transformFirebaseEvent, validateEventType } from './transforms';

// Initialize PostgreSQL client
if (!process.env.POSTGRES_HOST || !process.env.POSTGRES_DB || !process.env.POSTGRES_USER || !process.env.POSTGRES_PASSWORD) {
  console.error('Missing required PostgreSQL environment variables');
  process.exit(1);
}

const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: parseInt(process.env.POSTGRES_PORT || '5432'),
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  ssl: {
    rejectUnauthorized: false // For development only
  },
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 10000,
  max: 20
});

// Add error handler to the pool
pool.on('error', (err) => {
  console.error('Unexpected error on idle PostgreSQL client', err);
});

// Load environment variables from root .env
dotenv.config({ path: path.join(__dirname, '../../../../.env') });

// Initialize Firebase Admin
let firebaseInitialized = false;

if (!process.env.FIREBASE_PROJECT_ID || !process.env.FIREBASE_CLIENT_EMAIL || !process.env.FIREBASE_PRIVATE_KEY) {
  console.error('Missing Firebase credentials in environment variables');
} else {
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
      firebaseInitialized = true;
    }
  } catch (error) {
    console.error('Error initializing Firebase Admin:', error);
    console.warn('Starting server without Firebase authentication');
  }
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
      valid_types: ['leaderboard_create', 'tournament_create', 'quest_create', 'leaderboard_update', 'game_start', 'game_end', 'achievement', 
                   'score_update', 'kill', 'death', 'level_up', 'quest_progress', 
                   'item_acquire', 'custom']
    });
  }

  if (!firebaseInitialized) {
    console.warn('Firebase not initialized, skipping API key validation');
    req.body.studioId = 'test-studio';
    next();
    return;
  }

  try {
    // Find studio by API key
    const studioSnapshot = await admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .limit(1)
      .get();

    if (studioSnapshot.empty) {
      console.error('No studio found with API key:', apiKey);
      return res.status(401).json({ error: 'Invalid API key' });
    }

    const studio = studioSnapshot.docs[0];
    const studioData = studio.data();

    // Verify game ID belongs to this studio
    if (studioData.gameId !== event.gameId) {
      console.error('Game ID does not match studio:', { 
        studioId: studio.id, 
        expectedGameId: studioData.gameId,
        receivedGameId: event.gameId
      });
      return res.status(403).json({ error: 'Game ID does not belong to studio' });
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

  let redpandaConnected = false;
  try {
    await producer.connect();
    console.log('Connected to Redpanda');
    redpandaConnected = true;
  } catch (error) {
    console.error('Failed to connect to Redpanda:', error);
    console.warn('Starting server without Redpanda connection');
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

  // Quest creation endpoint
  app.post('/quests', validateEvent, async (req: express.Request, res: express.Response) => {
    console.log('Received quest creation request:', JSON.stringify(req.body, null, 2));
    try {
      const { gameId, type, data } = req.body;
      
      // Validate quest-specific fields
      if (!data.name || !data.description || !data.objectives) {
        return res.status(400).json({
          error: 'Missing required quest fields',
          required: ['name', 'description', 'objectives']
        });
      }

      interface QuestEvent {
        id: string;
        gameId: string;
        type: string;
        name: string;
        description: string;
        objectives: any[];
        startDate?: string;
        endDate?: string;
        requirements?: any;
        rewards?: any;
        createdAt: string;
      }

      const questEvent: QuestEvent = {
        id: crypto.randomUUID(),
        gameId,
        type,
        name: data.name,
        description: data.description,
        objectives: data.objectives,
        startDate: data.startDate,
        endDate: data.endDate,
        requirements: data.requirements,
        rewards: data.rewards,
        createdAt: new Date().toISOString()
      };

      console.log('Publishing quest event:', JSON.stringify(questEvent, null, 2));

      // Publish to Redpanda
      try {
        await producer.send({
          topic: 'quest.events',
          messages: [{
            key: questEvent.id,
            value: JSON.stringify(questEvent)
          }]
        });
        console.log('Quest event published to Redpanda');
      } catch (error) {
        console.error('Failed to publish quest event to Redpanda:', error);
        throw error;
      }

      // Return success response
      res.status(200).json({
        id: questEvent.id,
        status: 'processing',
        message: 'Quest creation event sent successfully'
      });
    } catch (error) {
      const err = error as Error;
      console.error('Error processing quest creation:', err);
      console.error('Stack:', err.stack);
      res.status(500).json({
        error: 'Failed to process quest creation',
        message: err.message,
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      });
    }
  });

  // Tournament creation endpoint
  // Leaderboard creation endpoint
  app.post('/leaderboards', validateEvent, async (req: express.Request, res: express.Response) => {
    console.log('Received leaderboard creation request:', JSON.stringify(req.body, null, 2));
    try {
      const { gameId, type, data } = req.body;

      // Validate leaderboard-specific fields
      if (!data.name || !data.eventType || !data.scoreField || !data.scoreType || !data.timePeriod) {
        return res.status(400).json({
          error: 'Missing required leaderboard fields',
          required: ['name', 'eventType', 'scoreField', 'scoreType', 'timePeriod']
        });
      }

      interface LeaderboardEvent {
        id: string;
        gameId: string;
        type: string;
        name: string;
        eventType: string;
        scoreField: string;
        scoreType: 'highest' | 'lowest' | 'sum';
        timePeriod: 'daily' | 'weekly' | 'monthly' | 'all-time';
        startDate: string;
        endDate?: string;
        isRolling: boolean;
        maxEntriesPerUser: number;
        highestScoresPerUser: number;
        requiredMetadata: string;
        createdAt: string;
      }

      const leaderboardEvent: LeaderboardEvent = {
        id: crypto.randomUUID(),
        gameId,
        type,
        name: data.name,
        eventType: data.eventType,
        scoreField: data.scoreField,
        scoreType: data.scoreType,
        timePeriod: data.timePeriod,
        startDate: data.startDate || new Date().toISOString(),
        endDate: data.endDate,
        isRolling: data.isRolling || false,
        maxEntriesPerUser: data.maxEntriesPerUser || 1000,
        highestScoresPerUser: data.highestScoresPerUser ? 1 : 0,
        requiredMetadata: JSON.stringify(data.requiredMetadata || []),
        createdAt: new Date().toISOString()
      };

      console.log('Publishing leaderboard event:', JSON.stringify(leaderboardEvent, null, 2));

      // Publish to Redpanda if connected
      if (redpandaConnected) {
        try {
          await producer.send({
            topic: 'leaderboard.events',
            messages: [{
              key: leaderboardEvent.id,
              value: JSON.stringify(leaderboardEvent)
            }]
          });
          console.log('Leaderboard event published to Redpanda');
        } catch (error) {
          console.error('Failed to publish leaderboard event to Redpanda:', error);
          // Continue without event publishing
          console.warn('Continuing without event publishing');
        }
      } else {
        console.warn('Skipping event publishing - Redpanda not connected');
      }

      // Return success response
      res.status(200).json({
        id: leaderboardEvent.id,
        status: 'processing',
        message: 'Leaderboard creation event sent successfully'
      });
    } catch (error) {
      const err = error as Error;
      console.error('Error processing leaderboard creation:', err);
      console.error('Stack:', err.stack);
      res.status(500).json({
        error: 'Failed to process leaderboard creation',
        message: err.message,
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      });
    }
  });

  app.post('/tournaments', validateEvent, async (req: express.Request, res: express.Response) => {
    console.log('Received tournament creation request:', JSON.stringify(req.body, null, 2));
    try {
      const { gameId, type, data } = req.body;
      
      // Validate tournament-specific fields
      if (!data.name || !data.description || !data.startDate || !data.endDate || !data.rewards) {
        return res.status(400).json({
          error: 'Missing required tournament fields',
          required: ['name', 'description', 'startDate', 'endDate', 'rewards']
        });
      }

      const tournamentEvent = {
        id: crypto.randomUUID(),
        gameId,
        type,
        name: data.name,
        description: data.description,
        startDate: data.startDate,
        endDate: data.endDate,
        requirements: data.requirements,
        rewards: data.rewards,
        rules: data.rules,
        maxParticipants: data.maxParticipants,
        createdAt: new Date().toISOString()
      };

      console.log('Publishing tournament event:', JSON.stringify(tournamentEvent, null, 2));

      // Publish to Redpanda
      try {
        await producer.send({
          topic: 'tournament.events',
          messages: [{
            key: tournamentEvent.id,
            value: JSON.stringify(tournamentEvent)
          }]
        });
        console.log('Tournament event published to Redpanda');
      } catch (error) {
        console.error('Failed to publish tournament event to Redpanda:', error);
        throw error;
      }

      // Return success response
      res.status(200).json({
        id: tournamentEvent.id,
        status: 'processing',
        message: 'Tournament creation event sent successfully'
      });
    } catch (error) {
      const err = error as Error;
      console.error('Error processing tournament creation:', err);
      console.error('Stack:', err.stack);
      res.status(500).json({
        error: 'Failed to process tournament creation',
        message: err.message,
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      });
    }
  });

  // Get a single leaderboard
  app.get('/leaderboards/:id', validateEvent, async (req: express.Request, res: express.Response) => {
    try {
      const { id } = req.params;
      
      const result = await pool.query(
        'SELECT * FROM leaderboards WHERE id = $1',
        [id]
      );

      if (result.rows.length === 0) {
        return res.status(404).json({ error: 'Leaderboard not found' });
      }

      res.status(200).json(result.rows[0]);
    } catch (error) {
      console.error('Error fetching leaderboard:', error);
      res.status(500).json({ error: 'Failed to fetch leaderboard' });
    }
  });

  // List leaderboards for a game
  app.get('/leaderboards', validateEvent, async (req: express.Request, res: express.Response) => {
    try {
      const { gameId } = req.query;
      
      if (!gameId) {
        return res.status(400).json({ error: 'gameId query parameter is required' });
      }

      console.log('Fetching leaderboards for game:', gameId);
      
      const result = await pool.query(
        'SELECT * FROM leaderboards WHERE game_id = $1 ORDER BY created_at DESC',
        [gameId]
      );

      console.log(`Found ${result.rows.length} leaderboards`);
      res.status(200).json(result.rows);
    } catch (error) {
      console.error('Error listing leaderboards:', error);
      res.status(500).json({ error: 'Failed to list leaderboards' });
    }
  });

  // Health check endpoint
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
