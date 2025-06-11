const { Pool } = require('pg');
const { spawn } = require('child_process');
require('dotenv').config();

// Initialize PostgreSQL client
const pool = new Pool({
  host: 'brightmatter-db.cwra0uc6su8r.us-east-1.rds.amazonaws.com',
  port: 5432,
  database: 'brightmatter',
  user: 'postgres',
  password: '2gL~5$_i-evP2!03w(7dUAU.]Miz',
  ssl: {
    rejectUnauthorized: false
  }
});

// Process game events
async function processGameEvent(event) {
  const { user_id, game_id, event_type, payload, timestamp } = event;
  
  try {
    await pool.query(
      `INSERT INTO game_events (user_id, game_id, event_type, payload, timestamp)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING event_id`,
      [user_id, game_id, event_type, payload, new Date(timestamp)]
    );
    console.log(`Processed game event: ${event_type} for user ${user_id}`);
  } catch (error) {
    console.error('Error processing game event:', error);
    throw error;
  }
}

// Process social posts
async function processSocialPost(post) {
  const {
    platform,
    creator_id,
    external_post_id,
    post_url,
    content_text,
    raw_metrics,
    campaign_id,
    timestamp
  } = post;

  try {
    await pool.query(
      `INSERT INTO social_posts 
       (platform, creator_id, external_post_id, post_url, content_text, raw_metrics, campaign_id, timestamp)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       RETURNING post_id`,
      [platform, creator_id, external_post_id, post_url, content_text, raw_metrics, campaign_id, new Date(timestamp)]
    );
    console.log(`Processed social post from ${platform} for creator ${creator_id}`);
  } catch (error) {
    console.error('Error processing social post:', error);
    throw error;
  }
}

// Process a message from any topic
async function processMessage(topic, message) {
  try {
    // Parse the rpk JSON output
    const data = JSON.parse(message);
    if (!data.value) {
      console.error('Invalid message format - no value:', message);
      return;
    }

    // Parse the actual event data
    const event = JSON.parse(data.value);
    if (topic === 'game.events.raw') {
      await processGameEvent(event);
    } else if (topic === 'social.posts.raw') {
      await processSocialPost(event);
    }
  } catch (error) {
    console.error(`Error processing message from topic ${topic}:`, error);
    console.error('Message was:', message);
  }
}

// Start consuming messages using rpk
function startConsumer(topic) {
  const consumer = spawn('rpk', ['topic', 'consume', topic]);

  consumer.stdout.on('data', (data) => {
    const message = data.toString().trim();
    if (message) {
      processMessage(topic, message);
    }
  });

  consumer.stderr.on('data', (data) => {
    console.error(`Error from ${topic} consumer:`, data.toString());
  });

  consumer.on('close', (code) => {
    console.log(`Consumer for ${topic} exited with code ${code}`);
    // Restart the consumer after a delay
    setTimeout(() => startConsumer(topic), 5000);
  });

  return consumer;
}

// Start all consumers
const consumers = [
  startConsumer('game.events.raw'),
  startConsumer('social.posts.raw')
];

// Handle graceful shutdown
const shutdown = async () => {
  try {
    // Kill all consumers
    consumers.forEach(consumer => consumer.kill());
    await pool.end();
    process.exit(0);
  } catch (error) {
    console.error('Error during shutdown:', error);
    process.exit(1);
  }
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

console.log('Event processor started...');

