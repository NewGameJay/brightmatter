const db = require('../config/database');
const { producer } = require('../config/redpanda');

class GameEventService {
  async ingestEvent(event) {
    try {
      // First, publish to Redpanda
      await producer.send({
        topic: 'game.events.raw',
        messages: [
          {
            key: event.game_id,
            value: JSON.stringify(event),
          },
        ],
      });

      // Then store in Postgres
      return await db.one(
        `INSERT INTO game_events(
          user_id, game_id, event_type, payload, timestamp
        ) VALUES($1, $2, $3, $4, $5) RETURNING event_id`,
        [
          event.user_id,
          event.game_id,
          event.event_type,
          event.payload,
          event.timestamp || new Date(),
        ]
      );
    } catch (error) {
      console.error('Error ingesting game event:', error);
      throw error;
    }
  }

  async getEventsByUser(userId, gameId, limit = 100) {
    try {
      return await db.any(
        `SELECT * FROM game_events 
         WHERE user_id = $1 
         AND ($2::varchar IS NULL OR game_id = $2)
         ORDER BY timestamp DESC 
         LIMIT $3`,
        [userId, gameId, limit]
      );
    } catch (error) {
      console.error('Error fetching user events:', error);
      throw error;
    }
  }
}

module.exports = new GameEventService();
