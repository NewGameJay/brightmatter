import { Handler } from '@netlify/functions';
import { Kafka } from 'kafkajs';
import * as admin from 'firebase-admin';
import { v4 as uuidv4 } from 'uuid';
import { Pool } from 'pg';

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

// Initialize PostgreSQL connection
const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: parseInt(process.env.POSTGRES_PORT || '5432'),
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  ssl: true
});

// Leaderboard types
type LeaderboardConfig = {
  gameId: string;
  name: string;
  eventType: string;
  scoreField: string;
  scoreType: 'highest' | 'lowest' | 'sum' | 'average';
  scoreFormula?: string;
  timePeriod: 'daily' | 'weekly' | 'monthly' | 'all_time';
  startDate?: string;
  endDate?: string;
  isRolling: boolean;
  maxEntriesPerUser: number;
  highestScoresPerUser: number;
  requiredMetadata: string[];
};

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

const producer = kafka.producer();

// Get available event types for leaderboards
const getEventTypes = async (event: any) => {
  if (event.httpMethod !== 'GET') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  const apiKey = event.headers['x-api-key'];
  if (!apiKey) {
    return {
      statusCode: 401,
      body: JSON.stringify({ error: 'API key required' })
    };
  }

  try {
    // Get game ID from Firebase
    const studio = await admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .limit(1)
      .get();

    if (studio.empty) {
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'Invalid API key' })
      };
    }

    // Query distinct event types from game_events table
    const result = await pool.query(
      'SELECT DISTINCT event_type, jsonb_object_keys(payload) as field FROM game_events WHERE game_id = $1',
      [studio.docs[0].id]
    );

    return {
      statusCode: 200,
      body: JSON.stringify({
        eventTypes: result.rows
      })
    };
  } catch (error) {
    console.error('Error getting event types:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Internal server error' })
    };
  }
};

// Handle leaderboard operations
const handleLeaderboards = async (event: any) => {
  const apiKey = event.headers['x-api-key'];
  if (!apiKey) {
    return {
      statusCode: 401,
      body: JSON.stringify({ error: 'API key required' })
    };
  }

  try {
    // Get game ID from Firebase
    const studio = await admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .limit(1)
      .get();

    if (studio.empty) {
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'Invalid API key' })
      };
    }

    const gameId = studio.docs[0].id;

    switch (event.httpMethod) {
      case 'GET':
        // Get leaderboard(s)
        const leaderboardId = event.queryStringParameters?.id;
        if (leaderboardId) {
          // Get specific leaderboard with entries
          const result = await pool.query(
            `SELECT l.*, 
                    json_agg(json_build_object(
                      'rank', le.rank,
                      'player_id', le.player_id,
                      'player_name', le.player_name,
                      'score', le.score,
                      'metadata', le.metadata,
                      'achieved_at', le.achieved_at
                    ) ORDER BY le.rank) as entries
             FROM leaderboards l
             LEFT JOIN leaderboard_entries le ON l.id = le.leaderboard_id
             WHERE l.id = $1 AND l.game_id = $2
             GROUP BY l.id`,
            [leaderboardId, gameId]
          );

          return {
            statusCode: 200,
            body: JSON.stringify(result.rows[0] || null)
          };
        } else {
          // List all leaderboards for the game
          const result = await pool.query(
            'SELECT * FROM leaderboards WHERE game_id = $1',
            [gameId]
          );

          return {
            statusCode: 200,
            body: JSON.stringify(result.rows)
          };
        }

      case 'POST':
        // Create new leaderboard
        const config: LeaderboardConfig = JSON.parse(event.body);
        const result = await pool.query(
          `INSERT INTO leaderboards (
            game_id, name, event_type, score_field, score_type,
            score_formula, time_period, start_date, end_date,
            is_rolling, max_entries_per_user, highest_scores_per_user,
            required_metadata
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
          RETURNING *`,
          [
            gameId,
            config.name,
            config.eventType,
            config.scoreField,
            config.scoreType,
            config.scoreFormula,
            config.timePeriod,
            config.startDate,
            config.endDate,
            config.isRolling,
            config.maxEntriesPerUser,
            config.highestScoresPerUser,
            JSON.stringify(config.requiredMetadata)
          ]
        );

        return {
          statusCode: 201,
          body: JSON.stringify(result.rows[0])
        };

      default:
        return {
          statusCode: 405,
          body: JSON.stringify({ error: 'Method not allowed' })
        };
    }
  } catch (error) {
    console.error('Error handling leaderboard:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Internal server error' })
    };
  }
};

export const handler: Handler = async (event, context) => {
  const path = event.path.replace('/.netlify/functions/api', '');
  
  // Handle different endpoints
  switch (path) {
    case '/events':
      return handleGameEvent(event);
    case '/leaderboards':
      return handleLeaderboards(event);
    case '/leaderboards/types':
      return getEventTypes(event);
    default:
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
