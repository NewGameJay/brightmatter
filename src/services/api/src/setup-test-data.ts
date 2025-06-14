import * as admin from 'firebase-admin';
import * as dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../../.env') });

// Initialize Firebase Admin
admin.initializeApp({
  credential: admin.credential.cert({
    projectId: process.env.FIREBASE_PROJECT_ID,
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
  })
});

async function setupTestData() {
  try {
    const studioId = '8yShyuMMP5RLtdRwosMdY0KXUIz1';
    const apiKey = 'YOUR-TEST-API-KEY';
    const gameId = 'brightmatter-test';

    // Add test studio
    await admin.firestore().collection('studios').doc(studioId).set({
      studioId,
      email: 'josh+8@ngplus.me',
      name: 'test studio 8',
      apiKey,
      features: {
        affiliates: true,
        communities: true,
        creatorProgram: true,
        leaderboards: true,
        matchmaking: true,
        quests: true,
        tournaments: true
      },
      subscriptionStatus: 'active',
      tier: 'ecosystem',
      games: [gameId],
      createdAt: new Date('2025-04-24T22:44:13-04:00'),
      updatedAt: new Date('2025-04-24T22:44:13-04:00')
    });

    // Add test game
    await admin.firestore().collection('games').doc(gameId).set({
      id: gameId,
      name: 'BrightMatter Test Game',
      studioId,
      active: true,
      createdAt: new Date('2025-04-24T22:44:13-04:00')
    });

    console.log('Test data setup complete');
    process.exit(0);
  } catch (error) {
    console.error('Error setting up test data:', error);
    process.exit(1);
  }
}

setupTestData();
