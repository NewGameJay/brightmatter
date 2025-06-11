const express = require('express');
const router = express.Router();
const { verifyToken } = require('../config/firebase');
const gameEventService = require('../services/gameEventService');

// Middleware to verify Firebase token
const verifyToken = async (req, res, next) => {
  try {
    const token = req.headers.authorization?.split('Bearer ')[1];
    if (!token) {
      return res.status(401).json({ error: 'No token provided' });
    }
    
    const decodedToken = await verifyToken(token);
    req.user = decodedToken;
    next();
  } catch (error) {
    res.status(401).json({ error: 'Invalid token' });
  }
};

// Ingest a new game event
router.post('/', verifyToken, async (req, res) => {
  try {
    const event = {
      user_id: req.user.uid,
      ...req.body,
    };
    
    const result = await gameEventService.ingestEvent(event);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get events for a user
router.get('/user/:gameId?', verifyToken, async (req, res) => {
  try {
    const events = await gameEventService.getEventsByUser(
      req.user.uid,
      req.params.gameId
    );
    res.json(events);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
