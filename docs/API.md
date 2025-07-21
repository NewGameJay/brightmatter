# BrightMatter API Documentation

## Authentication
All API endpoints require authentication using an API key provided by BrightMatter. Include this key in the `x-api-key` header with every request.

```http
x-api-key: YOUR-API-KEY
```

## Base URL
```
https://api.brightmatter.com
```

## Endpoints

### 1. Leaderboards
Create and manage game leaderboards.

#### Create Leaderboard
```http
POST /leaderboards
```

**Request Body:**
```json
{
  "gameId": "string",
  "type": "leaderboard_create",
  "data": {
    "name": "string",
    "eventType": "string",
    "scoreField": "string",
    "scoreType": "highest | lowest | sum",
    "timePeriod": "daily | weekly | monthly | all-time",
    "startDate": "ISO8601 timestamp",
    "endDate": "ISO8601 timestamp",
    "isRolling": "boolean",
    "maxEntriesPerUser": "number",
    "highestScoresPerUser": "boolean",
    "requiredMetadata": "string[]"
  }
}
```

**Field Constraints:**
- `gameId`: Must match a game ID in your studio's games list
- `name`: 3-50 characters, alphanumeric and spaces
- `eventType`: Must match a valid event type in your game
- `scoreField`: Must be a field present in your event data
- `timePeriod`: One of: daily, weekly, monthly, all-time
- `startDate`, `endDate`: ISO8601 format, endDate must be after startDate
- `maxEntriesPerUser`: 1-1000
- `requiredMetadata`: Array of metadata fields required for entry validation

**Response:**
```json
{
  "id": "UUID",
  "status": "processing",
  "message": "Leaderboard creation event sent successfully"
}
```

### 2. Quests
Create and manage game quests.

#### Create Quest
```http
POST /quests
```

**Request Body:**
```json
{
  "gameId": "string",
  "type": "quest_create",
  "data": {
    "name": "string",
    "description": "string",
    "objectives": [
      {
        "type": "string",
        "target": "string",
        "count": "number"
      }
    ],
    "startDate": "ISO8601 timestamp",
    "endDate": "ISO8601 timestamp",
    "requirements": {
      "level": "number",
      "items": "string[]"
    },
    "rewards": {
      "experience": "number",
      "items": "string[]"
    }
  }
}
```

**Field Constraints:**
- `gameId`: Must match a game ID in your studio's games list
- `name`: 3-50 characters, alphanumeric and spaces
- `description`: 10-500 characters
- `objectives`: Array of 1-10 objectives
  - `type`: One of: kill, collect, achieve, visit, complete
  - `count`: 1-1000000
- `requirements`: Optional quest prerequisites
  - `level`: 1-100
  - `items`: Array of required item IDs
- `rewards`: Required rewards structure
  - `experience`: 0-1000000
  - `items`: Array of item IDs to award

**Response:**
```json
{
  "id": "UUID",
  "status": "processing",
  "message": "Quest creation event sent successfully"
}
```

### 3. Tournaments
Create and manage game tournaments.

#### Create Tournament
```http
POST /tournaments
```

**Request Body:**
```json
{
  "gameId": "string",
  "type": "tournament_create",
  "data": {
    "name": "string",
    "description": "string",
    "startDate": "ISO8601 timestamp",
    "endDate": "ISO8601 timestamp",
    "requirements": {
      "minLevel": "number",
      "maxLevel": "number"
    },
    "rewards": {
      "first": "number",
      "second": "number",
      "third": "number"
    },
    "rules": "string[]",
    "maxParticipants": "number"
  }
}
```

**Field Constraints:**
- `gameId`: Must match a game ID in your studio's games list
- `name`: 3-50 characters, alphanumeric and spaces
- `description`: 10-500 characters
- `startDate`, `endDate`: ISO8601 format, endDate must be after startDate
- `requirements`: Optional tournament prerequisites
  - `minLevel`: 1-100
  - `maxLevel`: 1-100, must be >= minLevel
- `rewards`: Required rewards structure
  - Values must be positive numbers
  - At least first place reward required
- `rules`: Array of 0-10 rule strings
- `maxParticipants`: 2-1000

**Response:**
```json
{
  "id": "UUID",
  "status": "processing",
  "message": "Tournament creation event sent successfully"
}
```

## Event Types
All events are published to dedicated Redpanda topics and follow a consistent pattern:

### Event Topics
- `leaderboard.events`: Leaderboard creation and updates
- `quest.events`: Quest creation and updates
- `tournament.events`: Tournament creation and updates

### Event Structure
```json
{
  "id": "UUID",
  "gameId": "string",
  "type": "string",
  "data": "object",
  "createdAt": "ISO8601 timestamp"
}
```

### Event Types
1. Leaderboard Events:
   - `leaderboard_create`: Create new leaderboard
   - `leaderboard_update`: Update existing leaderboard

2. Quest Events:
   - `quest_create`: Create new quest
   - `quest_update`: Update existing quest
   - `quest_complete`: Mark quest as completed
   - `quest_fail`: Mark quest as failed

3. Tournament Events:
   - `tournament_create`: Create new tournament
   - `tournament_update`: Update tournament details
   - `tournament_join`: Player joins tournament
   - `tournament_complete`: Tournament completion with results

## Database Schemas

### Leaderboards
```sql
CREATE TABLE leaderboards (
    id UUID PRIMARY KEY,
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    score_field VARCHAR(255) NOT NULL,
    score_type VARCHAR(50) NOT NULL,
    time_period VARCHAR(50) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    is_rolling BOOLEAN NOT NULL,
    max_entries_per_user INTEGER NOT NULL,
    highest_scores_per_user BOOLEAN NOT NULL,
    required_metadata JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

### Quests
```sql
CREATE TABLE quests (
    id UUID PRIMARY KEY,
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    objectives JSONB NOT NULL,
    rewards JSONB NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    requirements JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE quest_progress (
    id UUID PRIMARY KEY,
    quest_id UUID NOT NULL REFERENCES quests(id),
    player_id VARCHAR(255) NOT NULL,
    objectives_progress JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

### Tournaments
```sql
CREATE TABLE tournaments (
    id UUID PRIMARY KEY,
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    requirements JSONB,
    rewards JSONB NOT NULL,
    rules JSONB,
    max_participants INTEGER,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE tournament_participants (
    id UUID PRIMARY KEY,
    tournament_id UUID NOT NULL REFERENCES tournaments(id),
    player_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(255) NOT NULL,
    score NUMERIC DEFAULT 0,
    rank INTEGER,
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE tournament_history (
    id UUID PRIMARY KEY,
    tournament_id UUID NOT NULL REFERENCES tournaments(id),
    winners JSONB NOT NULL,
    total_participants INTEGER NOT NULL,
    final_scores JSONB NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

## Error Responses

### Common Error Codes
- `400`: Bad Request - Invalid input data
- `401`: Unauthorized - Invalid or missing API key
- `403`: Forbidden - API key valid but no access to gameId
- `404`: Not Found - Resource not found
- `409`: Conflict - Resource already exists
- `422`: Unprocessable Entity - Valid request but failed validation
- `500`: Internal Server Error - Server error, try again later

### Error Response Format
```json
{
  "error": "string",
  "details": "string",
  "code": "number"
}
```
