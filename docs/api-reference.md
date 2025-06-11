# API Reference

## Event Ingestion Endpoint

### POST /events

Send game events to the BrightMatter platform.

**Production Endpoint:** `https://api.brightmatter.io/events`

**Development Endpoint:** `http://localhost:3001/events`

**Headers:**
```http
Content-Type: application/json
```

**Headers:**
```http
Content-Type: application/json
x-api-key: your_api_key
```

**Request Body:**
```json
{
  "gameId": "your_game_id",
  "type": "event_type",
  "data": {
    /* Event specific data */
  }
  "type": "kill",
  "timestamp": "2025-06-09T20:30:53Z",
  "metadata": {
    "platform": "windows",
    "sdkVersion": "1.0.0",
    "buildHash": "release-1.2.3",
    "apiKey": "your_api_key",
    "weapon": "sword",
    "target": "dragon",
    "points": 100
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Event received",
  "event_id": "game_123_1686341453123"
}
```

**Required Fields:**
- `gameId`: Your game's unique identifier
- `studioId`: Your studio's unique identifier
- `playerId`: Unique identifier for the player
- `playerName`: Display name of the player
- `type`: Event type (see [Event Types](./event-types.md))
- `timestamp`: ISO 8601 timestamp
- `metadata`: Object containing:
  - `platform`: Gaming platform (e.g., "windows", "ps5", "xbox", "mobile")
  - `sdkVersion`: Version of your game's SDK
  - `buildHash`: Game build identifier
  - `apiKey`: Your API key
  - Additional event-specific data

**Error Responses:**

1. Invalid Credentials (401):
```json
{
  "error": "Invalid game credentials"
}
```

2. Missing Fields (400):
```json
{
  "error": "Missing required fields",
  "required": ["gameId", "playerId", "type", "studioId"]
}
```

3. Invalid Event Type (400):
```json
{
  "error": "Invalid event type",
  "valid_types": ["leaderboard_update", "game_start", "game_end", ...]
}
```

4. Server Error (500):
```json
{
  "error": "Failed to process event",
  "message": "Error details"
}
```
