import * as admin from 'firebase-admin';
import path from 'path';
import dotenv from 'dotenv';

// Load environment variables from root .env
dotenv.config({ path: '/Users/jflo7006/Downloads/BOREDGAMER/CascadeProjects/brightmatter/.env' });

// Initialize Firebase Admin
if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID!,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL!,
      privateKey: process.env.FIREBASE_PRIVATE_KEY!.replace(/\\n/g, '\n')
    })
  });
}

async function setupTestGame() {
  try {
    // Create a test studio
    const studioRef = await admin.firestore().collection('studios').add({
      name: 'Test Studio',
      apiKey: 'test-api-key-123',
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('Created test studio with ID:', studioRef.id);

    // Create a test game
    const gameRef = await admin.firestore().collection('games').doc('test-game').set({
      name: 'Test Game',
      studioId: studioRef.id,
      apiKey: 'test-api-key-123',
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('Created test game: test-game');

    console.log('Test setup complete. Use these credentials for API calls:');
    console.log('gameId: test-game');
    console.log('x-api-key: test-api-key-123');
  } catch (error) {
    console.error('Error setting up test data:', error);
  } finally {
    admin.app().delete();
  }
}

setupTestGame();
