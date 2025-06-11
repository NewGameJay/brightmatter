import * as admin from 'firebase-admin';
import * as dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../../.env') });

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
    // Add test game
    await admin.firestore().collection('games').doc('test-game').set({
      id: 'test-game',
      name: 'Test Game',
      studioId: 'test-studio',
      active: true,
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('Test data setup complete');
    process.exit(0);
  } catch (error) {
    console.error('Error setting up test data:', error);
    process.exit(1);
  }
}

setupTestData();
