const { execSync } = require('child_process');
const path = require('path');

// Sample game event
const gameEvent = {
  user_id: 'test_user_123',
  game_id: 'game_123',
  event_type: 'kill',
  payload: {
    weapon: 'sword',
    target: 'dragon',
    points: 100
  },
  timestamp: new Date().toISOString()
};

// Sample social post
const socialPost = {
  platform: 'youtube',
  creator_id: 'creator_123',
  external_post_id: 'yt_123456',
  post_url: 'https://youtube.com/watch?v=123456',
  content_text: 'Check out my awesome gameplay!',
  raw_metrics: {
    views: 1000,
    likes: 150,
    comments: 45
  },
  timestamp: new Date().toISOString()
};

function produceEvent(topic, message) {
  const scriptPath = path.join(__dirname, 'produce-event.sh');
  try {
    const output = execSync(`${scriptPath} ${topic} '${JSON.stringify(message)}'`, {
      encoding: 'utf8'
    });
    console.log(`Produced message to ${topic}:`, output);
    return true;
  } catch (error) {
    console.error(`Error producing message to ${topic}:`, error);
    return false;
  }
}

// Produce test events
console.log('Producing test events...');
produceEvent('game.events.raw', gameEvent);
produceEvent('social.posts.raw', socialPost);

