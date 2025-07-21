# Frontend Integration Guide

## Overview
This guide explains how to integrate your frontend application with the BrightMatter API for leaderboards, quests, and tournaments.

## Prerequisites
1. BrightMatter API Key
2. Game ID registered with BrightMatter
3. Frontend HTTP client (e.g., Axios, Fetch)

## API Client Setup

### Using Axios
```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'https://api.brightmatter.com',
  headers: {
    'Content-Type': 'application/json',
    'x-api-key': 'YOUR-API-KEY'
  }
});
```

### Using Fetch
```javascript
const API_BASE = 'https://api.brightmatter.com';
const API_KEY = 'YOUR-API-KEY';

async function apiRequest(endpoint, method = 'GET', data = null) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': API_KEY
    }
  };

  if (data) {
    options.body = JSON.stringify(data);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, options);
  return response.json();
}
```

## Integration Examples

### 1. Leaderboards

#### Create a Leaderboard
```javascript
// Using Axios
async function createLeaderboard(gameId, name, config) {
  try {
    const response = await api.post('/leaderboards', {
      gameId,
      type: 'leaderboard_create',
      data: {
        name,
        ...config
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error creating leaderboard:', error);
    throw error;
  }
}

// Example usage
const leaderboardConfig = {
  eventType: 'player_score',
  scoreField: 'score',
  scoreType: 'highest',
  timePeriod: 'weekly',
  startDate: new Date().toISOString(),
  endDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
  isRolling: false,
  maxEntriesPerUser: 1,
  highestScoresPerUser: true,
  requiredMetadata: ['level', 'character']
};

const result = await createLeaderboard('my-game-id', 'Weekly High Scores', leaderboardConfig);
```

### 2. Quests

#### Create a Quest
```javascript
async function createQuest(gameId, questData) {
  try {
    const response = await api.post('/quests', {
      gameId,
      type: 'quest_create',
      data: questData
    });
    return response.data;
  } catch (error) {
    console.error('Error creating quest:', error);
    throw error;
  }
}

// Example usage
const questData = {
  name: 'Dragon Slayer',
  description: 'Defeat the mighty dragon and collect its scales',
  objectives: [
    { type: 'kill', target: 'dragon', count: 1 },
    { type: 'collect', target: 'dragon_scale', count: 5 }
  ],
  rewards: {
    experience: 1000,
    items: ['dragon_sword', 'dragon_shield']
  }
};

const result = await createQuest('my-game-id', questData);
```

### 3. Tournaments

#### Create a Tournament
```javascript
async function createTournament(gameId, tournamentData) {
  try {
    const response = await api.post('/tournaments', {
      gameId,
      type: 'tournament_create',
      data: tournamentData
    });
    return response.data;
  } catch (error) {
    console.error('Error creating tournament:', error);
    throw error;
  }
}

// Example usage
const tournamentData = {
  name: 'Weekly Challenge',
  description: 'Get the highest score in a week',
  startDate: new Date().toISOString(),
  endDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
  requirements: {
    minLevel: 10,
    maxLevel: 50
  },
  rewards: {
    first: 1000,
    second: 500,
    third: 250
  },
  rules: ['No cheating', 'One entry per player'],
  maxParticipants: 100
};

const result = await createTournament('my-game-id', tournamentData);
```

## Error Handling

### Response Structure
All API responses follow a consistent structure:

**Success Response:**
```javascript
{
  id: 'UUID',
  status: 'processing',
  message: 'Event sent successfully'
}
```

**Error Response:**
```javascript
{
  error: 'Error message',
  details: 'Detailed error description',
  code: 400 // HTTP status code
}
```

### Error Handling Example
```javascript
async function handleApiRequest(requestFn) {
  try {
    const result = await requestFn();
    return result;
  } catch (error) {
    if (error.response) {
      // Server responded with error
      const { status, data } = error.response;
      
      switch (status) {
        case 400:
          console.error('Invalid request:', data.details);
          break;
        case 401:
          console.error('Invalid API key');
          // Handle authentication error
          break;
        case 403:
          console.error('No access to game ID');
          break;
        case 409:
          console.error('Resource conflict:', data.details);
          break;
        case 422:
          console.error('Validation failed:', data.details);
          break;
        default:
          console.error('Server error:', data.error);
      }
    } else if (error.request) {
      // Request made but no response
      console.error('No response from server');
    } else {
      // Request setup error
      console.error('Request error:', error.message);
    }
    throw error;
  }
}
```

## TypeScript Types

```typescript
// Common types
interface ApiResponse<T> {
  id: string;
  status: 'processing' | 'completed' | 'failed';
  message: string;
  data?: T;
}

interface ApiError {
  error: string;
  details?: string;
  code: number;
}

// Leaderboard types
interface LeaderboardConfig {
  name: string;
  eventType: string;
  scoreField: string;
  scoreType: 'highest' | 'lowest' | 'sum';
  timePeriod: 'daily' | 'weekly' | 'monthly' | 'all-time';
  startDate: string;
  endDate: string;
  isRolling: boolean;
  maxEntriesPerUser: number;
  highestScoresPerUser: boolean;
  requiredMetadata: string[];
}

// Quest types
interface QuestObjective {
  type: 'kill' | 'collect' | 'achieve' | 'visit' | 'complete';
  target: string;
  count: number;
}

interface QuestConfig {
  name: string;
  description: string;
  objectives: QuestObjective[];
  rewards: {
    experience: number;
    items: string[];
  };
  requirements?: {
    level: number;
    items: string[];
  };
  startDate?: string;
  endDate?: string;
}

// Tournament types
interface TournamentConfig {
  name: string;
  description: string;
  startDate: string;
  endDate: string;
  requirements?: {
    minLevel: number;
    maxLevel: number;
  };
  rewards: {
    first: number;
    second?: number;
    third?: number;
  };
  rules?: string[];
  maxParticipants?: number;
}
```

## Best Practices

1. **Error Handling**
   - Always implement proper error handling
   - Check for specific error codes and handle accordingly
   - Log errors for debugging

2. **Date Handling**
   - Always use ISO8601 format for dates
   - Consider timezone differences
   - Validate date ranges before sending

3. **Validation**
   - Validate data on the frontend before sending
   - Follow field constraints from API docs
   - Handle validation errors gracefully

4. **API Key Security**
   - Never expose API key in frontend code
   - Use environment variables
   - Implement proper key rotation

5. **Rate Limiting**
   - Implement retry logic with exponential backoff
   - Cache responses when appropriate
   - Monitor API usage
