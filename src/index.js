const express = require('express');
const { producer, consumer } = require('./config/redpanda');
require('dotenv').config();

const app = express();
app.use(express.json());

// Routes
app.use('/api/game-events', require('./routes/gameEvents'));

// Connect to Redpanda
async function connectServices() {
  try {
    await producer.connect();
    await consumer.connect();
    
    // Subscribe to topics
    await consumer.subscribe({
      topics: ['game.events.raw'],
      fromBeginning: true
    });

    // Start consuming messages
    await consumer.run({
      eachMessage: async ({ topic, partition, message }) => {
        console.log({
          topic,
          partition,
          offset: message.offset,
          value: message.value.toString(),
        });
        // TODO: Add message processing logic
      },
    });

    console.log('Connected to Redpanda');
  } catch (error) {
    console.error('Error connecting to Redpanda:', error);
    process.exit(1);
  }
}

const PORT = process.env.PORT || 3000;

app.listen(PORT, async () => {
  console.log(`Server running on port ${PORT}`);
  await connectServices();
});
