const admin = require('firebase-admin');
require('dotenv').config();

// Initialize Firebase app
const app = admin.initializeApp({
  credential: admin.credential.cert({
    projectId: process.env.FIREBASE_PROJECT_ID,
    privateKey: process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n'),
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
  }),
});

// Helper function to verify tokens
const verifyToken = (token) => app.auth().verifyIdToken(token);

module.exports = {
  app,
  verifyToken,
  // Firestore references
  db: app.firestore(),
  auth: app.auth(),
};
