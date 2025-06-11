import { Handler } from '@netlify/functions';
import * as admin from 'firebase-admin';

// Initialize Firebase Admin
let app: admin.app.App;
try {
  app = admin.app();
} catch {
  app = admin.initializeApp({
    credential: admin.credential.cert({
      projectId: process.env.FIREBASE_PROJECT_ID,
      clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
      privateKey: process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n')
    })
  });
}

export const handler: Handler = async (event) => {
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

    // Verify API key and game ID
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

    // Store event in Firestore
    const eventRef = await admin.firestore()
      .collection('events')
      .add({
        ...body,
        timestamp: admin.firestore.FieldValue.serverTimestamp(),
        studioId: studio.docs[0].id
      });

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        event: {
          id: eventRef.id,
          type: body.type,
          gameId: body.gameId
        }
      })
    };
  } catch (error) {
    console.error('Error processing event:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: 'Failed to process event'
      })
    };
  }
};
