import axios from 'axios';
import { FirebaseEvent } from './types';

const testEvent: FirebaseEvent = {
  leaderboardId: "global",
  gameId: "AssasinsCreed_Shadows",
  playerId: "test_player1",
  playerName: "TestPlayer",
  score: 5000,
  timeframe: "daily",
  timestamp: new Date().toISOString(),
  type: "leaderboard_update",
  metadata: {
    platform: "windows",
    sdkVersion: "1.0.0",
    buildHash: "++UE4+Release-4.27-CL-123456789",
    apiKey: "bg_i_n3q4c37dwg8",
    // Add any other metadata fields needed
    region: "us-east",
    sessionId: "test-session-1",
    clientVersion: "1.0.0"
  },
  studioId: "Ubisoft"
};

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function sendTestEvent() {
  // Wait for server to be ready
  await delay(1000);
  try {
    const response = await axios.post('http://localhost:3001/events', testEvent);
    console.log('Event sent successfully:', response.data);
  } catch (error: any) {
    console.error('Error sending event:');
    if (error.response) {
      // Server responded with error
      console.error('Status:', error.response.status);
      console.error('Data:', error.response.data);
    } else if (error.request) {
      // Request made but no response
      console.error('No response received');
    } else {
      // Error setting up request
      console.error('Error:', error.message);
    }
    console.error('Stack:', error.stack);
    process.exit(1);
  }
}

sendTestEvent();
