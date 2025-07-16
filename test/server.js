const express = require('express');
const { Kafka } = require('kafkajs');
const { TwitterApi } = require('twitter-api-v2');
const path = require('path');
require('dotenv').config({ path: '../.env' });

const app = express();
app.use(express.json());

// Serve static files
app.use(express.static(__dirname));

// Initialize Kafka client
const kafka = new Kafka({
    brokers: [process.env.REDPANDA_BROKERS],
    sasl: {
        mechanism: 'scram-sha-256',
        username: process.env.REDPANDA_USERNAME,
        password: process.env.REDPANDA_PASSWORD
    },
    ssl: true,
    clientId: process.env.REDPANDA_CLIENT_ID || 'brightmatter'
});

const producer = kafka.producer();

// Connect producer on startup
producer.connect().then(() => {
    console.log('Connected to Redpanda!');
}).catch(err => {
    console.error('Failed to connect to Redpanda:', err);
});

// Serve test page
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'connect-x.html'));
});

// Handle social connect request
app.post('/social/connect', async (req, res) => {
    try {
        const { userId, platform, action } = req.body;
        
        // Initialize Twitter client
        const twitterClient = new TwitterApi({
            clientId: process.env.TWITTER_CLIENT_ID || '',
            clientSecret: process.env.TWITTER_CLIENT_SECRET || '',
        });

        // Generate real OAuth URL
        const { url, codeVerifier, state } = await twitterClient.generateOAuth2AuthLink(
            process.env.TWITTER_CALLBACK_URL || 'https://api.brightmatter.io/auth/twitter/callback',
            { scope: ['tweet.read', 'users.read', 'offline.access'] }
        );

        // Send event to Redpanda
        await producer.send({
            topic: 'social.connect',
            messages: [{
                key: userId,
                value: JSON.stringify({
                    userId,
                    platform,
                    action,
                    timestamp: Date.now(),
                    state // Include state for verification
                })
            }]
        });

        console.log('Event sent to Redpanda:', req.body);
        console.log('OAuth URL generated:', url);
        
        res.json({
            success: true,
            message: 'OAuth URL generated',
            authUrl: url,
            state
        });
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Handle shutdown
process.on('SIGTERM', async () => {
    try {
        await producer.disconnect();
        console.log('Disconnected from Redpanda');
        process.exit(0);
    } catch (error) {
        console.error('Error during shutdown:', error);
        process.exit(1);
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Test server running at http://localhost:${PORT}`);
});
