import * as admin from 'firebase-admin';
import * as dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../.env') });

// Initialize Firebase Admin
if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
    })
  });
}

async function setupGame() {
  try {
    const gameId = 'AssasinsCreed_Shadows';
    
    await admin.firestore()
      .collection('games')
      .doc(gameId)
      .set({
        apiKey: 'bg_i_n3q4c37dwg8',
        buildHash: '++UE4+Release-4.27-CL-123456789',
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        domain: 'newgame.me',
        email: 'josh@ngplus.me',
        features: {
          communities: true,
          creatorProgram: true,
          leaderboards: true,
          matchmaking: true,
          quests: true,
          tournaments: true
        },
        gameId: gameId,
        name: 'Ubisoft',
        studioId: 'Ubisoft',
        tier: 'ecosystem',
        updatedAt: admin.firestore.FieldValue.serverTimestamp()
      });

    console.log('Game created successfully');
    process.exit(0);
  } catch (error) {
    console.error('Error:', error);
    process.exit(1);
  }
}

setupGame();
