import { Pool } from 'pg';
import { Kafka } from 'kafkajs';
import dotenv from 'dotenv';
import path from 'path';
import { v5 as uuidv5 } from 'uuid';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../../.env') });

// Validate PostgreSQL environment variables
if (!process.env.POSTGRES_HOST || !process.env.POSTGRES_DB || !process.env.POSTGRES_USER || !process.env.POSTGRES_PASSWORD) {
  console.error('Missing required PostgreSQL environment variables');
  process.exit(1);
}

// Initialize PostgreSQL client
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

// Validate Redpanda environment variables
if (!process.env.REDPANDA_CLIENT_ID || !process.env.REDPANDA_BROKERS || !process.env.REDPANDA_USERNAME || !process.env.REDPANDA_PASSWORD) {
  console.error('Missing required Redpanda environment variables');
  process.exit(1);
}

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

const consumer = kafka.consumer({ groupId: 'social-auth-processor-group' });

interface TournamentEvent {
  id: string;
  gameId: string;
  name: string;
  description: string;
  format: 'single_elimination' | 'double_elimination' | 'round_robin' | 'swiss';
  startDate: string;
  endDate: string;
  registrationStartDate: string;
  registrationEndDate: string;
  maxParticipants: number;
  minParticipants: number;
  prizePool?: {
    currency: string;
    amount: number;
    distribution: Array<{
      position: number;
      percentage: number;
    }>;
  };
  rules: {
    scoreType: 'highest' | 'lowest' | 'sum';
    roundDuration: number;
    maxRounds: number;
    tiebreaker?: string;
  };
  requirements?: {
    minLevel?: number;
    maxLevel?: number;
    region?: string[];
    platform?: string[];
  };
  createdAt: string;
}

async function processTournamentEvent(event: TournamentEvent) {
  console.log('Processing tournament event:', {
    id: event.id,
    gameId: event.gameId,
    name: event.name
  });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Generate a deterministic UUID from the event ID using UUIDv5
    // We'll use a fixed namespace UUID for all tournament IDs
    const TOURNAMENT_NAMESPACE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8'; // UUID v4
    const tournamentId = uuidv5(event.id, TOURNAMENT_NAMESPACE);

    // Insert into tournaments table
    const query = `
      INSERT INTO tournaments (
        tournament_id,
        game_id,
        title,
        description,
        start_date,
        end_date,
        rules,
        status,
        created_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      ON CONFLICT (tournament_id) DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        rules = EXCLUDED.rules,
        status = EXCLUDED.status
    `;

    // Combine all tournament rules and requirements into a single rules JSONB
    const tournamentRules = {
      ...event.rules,
      maxParticipants: event.maxParticipants,
      requirements: event.requirements,
      prizePool: event.prizePool
    };

    const values = [
      tournamentId, // Use the generated UUID
      event.gameId,
      event.name,
      event.description,
      event.startDate,
      event.endDate,
      JSON.stringify(tournamentRules),
      'active', // Default status for new tournaments
      new Date().toISOString()
    ];

    console.log('Executing tournament insert/update query...');
    await client.query(query, values);
    console.log('Tournament stored in PostgreSQL:', event.id);

    await client.query('COMMIT');
  } catch (error) {
    console.error('Error processing tournament event:', error);
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function startConsumer() {
  try {
    console.log('Starting tournament consumer...');
    await consumer.connect();
    console.log('Connected to Redpanda');

    console.log('Subscribing to tournament.events topic...');
    await consumer.subscribe({
      topic: 'tournament.events',
      fromBeginning: true
    });
    console.log('Successfully subscribed to tournament.events topic');

    console.log('Starting message processing loop...');
    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        try {
          console.log('Received message:', {
            topic,
            partition,
            offset: message.offset,
            timestamp: message.timestamp
          });

          const event = JSON.parse(message.value?.toString() || '');
          console.log('Parsed tournament event:', {
            id: event.id,
            gameId: event.gameId,
            name: event.name,
            type: event.type
          });

          await processTournamentEvent(event);
          console.log('Successfully processed tournament event:', event.id);
        } catch (error) {
          console.error('Error processing tournament message:', error);
          console.error('Message details:', {
            topic,
            partition,
            offset: message.offset,
            key: message.key?.toString(),
            value: message.value?.toString()
          });
        }
      }
    });

    // Add HTTP server for health checks (required for Replit deployment)
    import http from 'http';

    const server = http.createServer((req, res) => {
      if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'healthy', service: 'tournament-processor' }));
      } else {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    server.listen(8080, '0.0.0.0', () => {
      console.log('Health check server running on port 8080');
    });

    console.log('Tournament Processor started. Listening for events...');

    // Keep the process running
    process.stdin.resume();
  } catch (error: unknown) {
    if (error instanceof Error) {
      console.error('Error starting tournament consumer:', error.message);
      console.error('Stack trace:', error.stack);
    } else {
      console.error('Unknown error starting tournament consumer:', error);
    }
    process.exit(1);
  }
}

// Handle graceful shutdown
process.on('SIGTERM', async () => {
  console.log('SIGTERM received, shutting down...');
  try {
    await consumer.disconnect();
    await pool.end();
    console.log('Disconnected from Redpanda and PostgreSQL');
  } catch (error) {
    console.error('Error during shutdown:', error);
  }
  process.exit(0);
});

// Start consumer and keep process running
startConsumer().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});

// Keep process running
process.stdin.resume();