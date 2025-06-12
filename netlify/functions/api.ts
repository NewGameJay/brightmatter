import { Handler } from '@netlify/functions';
import { Kafka, Partitioners } from 'kafkajs';
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
console.log('Initializing PostgreSQL pool with config:', {
  host: process.env.POSTGRES_HOST,
  port: process.env.POSTGRES_PORT || '5432',
  database: process.env.POSTGRES_DB,
  user: process.env.POSTGRES_USER ? 'set' : 'not set',
  password: process.env.POSTGRES_PASSWORD ? 'set' : 'not set',
  ssl: true
});

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

// Function to safely execute database queries with retries
async function executeQuery(queryText: string, values: any[] = [], maxRetries = 3) {
  let lastError: Error | unknown;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`PostgreSQL connection attempt ${attempt}/${maxRetries}...`);
      const client = await Promise.race([
        pool.connect(),
        new Promise<never>((_, reject) => 
          setTimeout(() => reject(new Error('Connection timeout')), 5000)
        )
      ]) as import('pg').PoolClient;

      try {
        console.log('Connected to PostgreSQL, executing query...');
        const result = await client.query(queryText, values);
        console.log('Query executed successfully');
        return result;
      } finally {
        client.release();
      }
    } catch (error) {
      console.error(`PostgreSQL attempt ${attempt} failed:`, error);
      lastError = error;
      if (attempt < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
        console.log(`Retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError;
}

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
    console.log('Querying event types for game:', studio.docs[0].id);
    const result = await executeQuery(
      'SELECT DISTINCT event_type, jsonb_object_keys(payload) as field FROM game_events WHERE game_id = $1',
      [studio.docs[0].id]
    );
    console.log('Found event types:', result.rows);

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
    console.log('Starting Firebase authentication for leaderboard operation...');
    console.log('API Key:', apiKey ? 'provided' : 'missing');
    console.log('Firebase config:', {
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL ? 'set' : 'not set',
      privateKey: process.env.FIREBASE_PRIVATE_KEY ? 'set' : 'not set'
    });

    const studioQuery = admin.firestore()
      .collection('studios')
      .where('apiKey', '==', apiKey)
      .limit(1);

    console.log('Executing Firebase query for leaderboard...');
    const studio = await studioQuery.get();
    console.log('Firebase query complete. Empty?', studio.empty);

    if (studio.empty) {
      console.log('No studio found with provided API key');
      return {
        statusCode: 401,
        body: JSON.stringify({ error: 'Invalid API key' })
      };
    }
    
    console.log('Studio found, proceeding with leaderboard request');
    const gameId = studio.docs[0].id;

    switch (event.httpMethod) {
      case 'GET':
        // Get leaderboard(s)
        const leaderboardId = event.queryStringParameters?.id;
        if (leaderboardId) {
          // Get specific leaderboard with entries
          console.log('Fetching leaderboard:', leaderboardId, 'for game:', gameId);
          const result = await executeQuery(
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
          console.log('Found leaderboard:', result.rows[0] ? 'yes' : 'no');

          return {
            statusCode: 200,
            body: JSON.stringify(result.rows[0] || null)
          };
        } else {
          // List all leaderboards for the game
          console.log('Listing leaderboards for game:', gameId);
          const result = await executeQuery(
            'SELECT * FROM leaderboards WHERE game_id = $1',
            [gameId]
          );
          console.log('Found', result.rows.length, 'leaderboards');

          return {
            statusCode: 200,
            body: JSON.stringify(result.rows)
          };
        }

      case 'POST': {
        // Parse request body
        const body = JSON.parse(event.body || '{}');

        // Generate leaderboard ID
        const leaderboardId = uuidv4();

        // Transform leaderboard config for BrightMatter format
        const brightMatterEvent = {
          id: leaderboardId,
          gameId,
          studioId: studio.docs[0].id,
          type: 'leaderboard.create',
          timestamp: new Date().toISOString(),
          config: {
            name: body.name,
            eventType: body.eventType,
            scoreField: body.scoreField,
            scoreType: body.scoreType,
            scoreFormula: body.scoreFormula,
            timePeriod: body.timePeriod,
            startDate: body.startDate,
            endDate: body.endDate,
            isRolling: body.isRolling,
            maxEntriesPerUser: body.maxEntriesPerUser,
            highestScoresPerUser: body.highestScoresPerUser,
            requiredMetadata: body.requiredMetadata || []
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

        // Send leaderboard creation event to Redpanda
        console.log('Sending leaderboard creation event to topic: leaderboard.events');
        await producer.send({
          topic: 'leaderboard.events',
          messages: [{
            key: gameId,
            value: JSON.stringify(brightMatterEvent)
          }]
        });

        // Disconnect from Redpanda
        await producer.disconnect();

        return {
          statusCode: 202,
          body: JSON.stringify({
            id: leaderboardId,
            status: 'processing',
            message: 'Leaderboard creation event sent successfully'
          })
        };
      }

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
