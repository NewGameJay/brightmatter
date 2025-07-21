# BrightMatter Integration Guide

## Architecture Overview
BrightMatter is an event-driven platform that processes social media data and generates AI insights. It uses:
- **Redpanda** as the primary event bus
- **PostgreSQL (RDS)** for durable storage
- **AWS ECS Fargate** for containerized services
- **Direct event emission** (no Firebase dependency)

## Event Flow

### 1. Social OAuth Integration
The OAuth flow follows these steps:

1. **Initial Connection**
   ```json
   // Emit to social.connect
   {
     "type": "CONNECT_TWITTER",
     "userId": "user-123",
     "platform": "twitter"
   }
   ```

2. **OAuth URL Generation**
   - BrightMatter generates OAuth URL
   - Returns URL via callback topic
   - Frontend redirects user to Twitter

3. **OAuth Callback**
   ```json
   // Emit to social.connect.callback
   {
     "type": "OAUTH_CALLBACK",
     "userId": "user-123",
     "code": "oauth-code-from-twitter",
     "state": "oauth-state"
   }
   ```

4. **Token Storage**
   - Tokens stored securely in RDS
   - Success/error events emitted

### 2. Current Topics

| Topic | Purpose | Example Payload |
|-------|---------|----------------|
| `social.connect` | Initial OAuth trigger | `{ "type": "CONNECT_TWITTER", "userId": "...", "platform": "twitter" }` |
| `social.connect.callback` | OAuth callback handling | `{ "type": "OAUTH_CALLBACK", "userId": "...", "code": "...", "state": "..." }` |
| `social.auth.error` | Error reporting | `{ "error": "description", "details": "..." }` |

## Integrating with BrightMatter

### 1. Prerequisites
- Redpanda credentials (SASL)
- Topic ACL permissions
- SSL/TLS enabled client

### 2. KafkaJS Configuration
```typescript
const kafka = new Kafka({
  clientId: process.env.REDPANDA_CLIENT_ID,
  brokers: [process.env.REDPANDA_BROKERS],
  ssl: {
    rejectUnauthorized: false // For Redpanda Cloud
  },
  sasl: {
    mechanism: 'scram-sha-256',
    username: process.env.REDPANDA_USERNAME,
    password: process.env.REDPANDA_PASSWORD
  }
});
```

### 3. Event Schema
All events must include:
- `type`: Event type identifier
- `userId`: Unique user identifier
- Additional fields based on event type

## Adding New Topics & Consumers

### 1. Topic Creation
1. Choose naming convention:
   - Entity-based: `entity.action` (e.g., `social.connect`)
   - Event-based: `domain.event` (e.g., `auth.completed`)

2. Configure ACLs:
   ```
   Topic Name: [your.topic.name]
   Permissions: Allow Read, Allow Write
   Consumer Group: [your-consumer-group]
   ```

### 2. Consumer Implementation
1. Create new consumer service:
   ```typescript
   const consumer = kafka.consumer({ 
     groupId: 'your-processor-group'
   });

   await consumer.subscribe({
     topics: ['your.topic.name']
   });
   ```

2. Containerize service:
   ```dockerfile
   FROM node:18-alpine
   WORKDIR /app
   COPY package*.json ./
   RUN npm install
   COPY . .
   RUN npm run build
   CMD ["npm", "run", "start"]
   ```

3. Deploy to ECS:
   - Create task definition
   - Configure environment variables
   - Set up CloudWatch logs

### 3. Best Practices
- One consumer group per processor
- Use transactions for data consistency
- Implement proper error handling
- Set up monitoring and alerts
- Document event schemas

## Database Schema

### social_accounts
```sql
CREATE TABLE social_accounts (
  user_id VARCHAR(255),
  platform VARCHAR(50),
  external_user_id VARCHAR(255),
  username VARCHAR(255),
  access_token TEXT,
  refresh_token TEXT,
  token_expires_at TIMESTAMP,
  scopes TEXT[],
  metadata JSONB,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  PRIMARY KEY (user_id, platform)
);
```

## Monitoring & Troubleshooting

### CloudWatch Logs
- Consumer logs: `/ecs/[service-name]`
- Error pattern: `ERROR`
- Kafka errors: `KafkaJS`

### Common Issues
1. Topic Authorization
   - Check ACL permissions
   - Verify SASL credentials
   - Confirm topic exists

2. SSL/TLS Issues
   - Use `rejectUnauthorized: false`
   - Verify broker URL format
   - Check SASL mechanism case

3. Consumer Group Errors
   - Verify group exists in ACLs
   - Check for duplicate group IDs
   - Monitor consumer lag

## Game Data Integration

### 1. Event Topics

| Topic | Purpose | Example Payload |
|-------|---------|----------------|
| `game.events` | Raw gameplay events | `{ "type": "GAME_EVENT", "userId": "...", "gameId": "...", "eventType": "SCORE", "data": { ... } }` |
| `leaderboard.events` | Leaderboard updates | `{ "type": "LEADERBOARD_UPDATE", "userId": "...", "score": 100, "metadata": { ... } }` |
| `quest.events` | Quest progress/completion | `{ "type": "QUEST_PROGRESS", "userId": "...", "questId": "...", "progress": 75 }` |
| `tournament.events` | Tournament participation | `{ "type": "TOURNAMENT_ENTRY", "userId": "...", "tournamentId": "...", "score": 500 }` |
| `affiliate.events` | Affiliate code usage | `{ "type": "AFFILIATE_USE", "userId": "...", "code": "CREATOR123", "action": "REDEEM" }` |

### 2. Database Schema

```sql
-- Game Events
CREATE TABLE game_events (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255),
  game_id VARCHAR(255),
  event_type VARCHAR(50),
  event_data JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  processed_at TIMESTAMP
);

-- Leaderboards
CREATE TABLE leaderboards (
  id SERIAL PRIMARY KEY,
  game_id VARCHAR(255),
  name VARCHAR(255),
  score_type VARCHAR(50),  -- highest, lowest, sum
  time_period VARCHAR(50), -- daily, weekly, monthly, all-time
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Leaderboard Entries
CREATE TABLE leaderboard_entries (
  id SERIAL PRIMARY KEY,
  leaderboard_id INTEGER REFERENCES leaderboards(id),
  user_id VARCHAR(255),
  score NUMERIC,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Quests
CREATE TABLE quests (
  id SERIAL PRIMARY KEY,
  game_id VARCHAR(255),
  title VARCHAR(255),
  description TEXT,
  requirements JSONB,
  reward_type VARCHAR(50),
  reward_amount INTEGER,
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Quest Progress
CREATE TABLE quest_progress (
  id SERIAL PRIMARY KEY,
  quest_id INTEGER REFERENCES quests(id),
  user_id VARCHAR(255),
  progress INTEGER,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Tournaments
CREATE TABLE tournaments (
  id SERIAL PRIMARY KEY,
  game_id VARCHAR(255),
  title VARCHAR(255),
  description TEXT,
  entry_fee INTEGER,
  prize_pool INTEGER,
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  rules JSONB,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Tournament Entries
CREATE TABLE tournament_entries (
  id SERIAL PRIMARY KEY,
  tournament_id INTEGER REFERENCES tournaments(id),
  user_id VARCHAR(255),
  score INTEGER,
  rank INTEGER,
  prize_amount INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Affiliate Codes
CREATE TABLE affiliate_codes (
  id SERIAL PRIMARY KEY,
  code VARCHAR(50) UNIQUE,
  creator_id VARCHAR(255),
  reward_type VARCHAR(50),
  reward_amount INTEGER,
  uses INTEGER DEFAULT 0,
  max_uses INTEGER,
  expires_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Affiliate Code Usage
CREATE TABLE affiliate_code_usage (
  id SERIAL PRIMARY KEY,
  code_id INTEGER REFERENCES affiliate_codes(id),
  user_id VARCHAR(255),
  reward_claimed BOOLEAN DEFAULT false,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### 3. Consumer Implementation

1. **Game Event Consumer**
   ```typescript
   // Process raw game events
   const gameConsumer = kafka.consumer({
     groupId: 'game-events-processor'
   });

   await gameConsumer.subscribe({
     topics: ['game.events']
   });

   await gameConsumer.run({
     eachMessage: async ({ message }) => {
       const event = JSON.parse(message.value.toString());
       
       // Store raw event
       await storeGameEvent(event);
       
       // Process for leaderboards/quests/tournaments
       await processGameEvent(event);
     }
   });
   ```

2. **Leaderboard Consumer**
   ```typescript
   const leaderboardConsumer = kafka.consumer({
     groupId: 'leaderboard-processor'
   });

   await leaderboardConsumer.subscribe({
     topics: ['leaderboard.events']
   });

   await leaderboardConsumer.run({
     eachMessage: async ({ message }) => {
       const event = JSON.parse(message.value.toString());
       
       // Update leaderboard
       await updateLeaderboard(event);
       
       // Check for tournament implications
       await checkTournamentStatus(event);
     }
   });
   ```

### 4. Integration Steps

1. **Topic Setup**
   - Create required topics in Redpanda
   - Configure ACLs for read/write access
   - Set up consumer groups

2. **Database Setup**
   - Execute schema creation scripts
   - Set up indexes for performance
   - Configure backup strategy

3. **Deploy Consumers**
   - Build and push Docker images
   - Create ECS task definitions
   - Configure environment variables
   - Deploy services

4. **Monitoring Setup**
   - Create CloudWatch dashboards
   - Set up alerts for:
     - Consumer lag
     - Error rates
     - Processing delays

### 5. Best Practices

1. **Event Processing**
   - Validate all incoming events
   - Use transactions for related updates
   - Implement idempotency checks
   - Handle duplicates gracefully

2. **Performance**
   - Batch database operations
   - Use appropriate indexes
   - Cache frequently accessed data
   - Monitor query performance

3. **Error Handling**
   - Implement dead letter queues
   - Log detailed error information
   - Set up retry mechanisms
   - Alert on critical failures

## Support
For integration support:
1. Check CloudWatch logs
2. Review ACL permissions
3. Verify event schema
4. Contact BrightMatter team
  ```sql
  CREATE TABLE social_accounts (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, platform)
  );
  ```
✅ Security groups configured
✅ SSL/TLS encryption enabled

### 3. Social Auth Processor
✅ TypeScript consumer service created
✅ Handles OAuth flows for:
  - Twitter/X (implemented)
  - YouTube (planned)
  - TikTok (planned)
✅ Docker container built and published
✅ ECS task definition created
✅ Service deployed and running

### 4. AWS Infrastructure
✅ ECS Fargate cluster operational
✅ Task execution role configured
✅ Service role configured
✅ Security groups set up
✅ SSM parameters created for secrets:
  - RDS credentials
  - Redpanda credentials
  - Twitter OAuth credentials
✅ CloudWatch logging configured

### 5. OAuth Implementation
✅ Twitter OAuth 2.0 flow implemented:
  - URL generation
  - State management
  - Token exchange
  - User info retrieval
✅ Secure token storage in RDS
✅ Refresh token handling
✅ Error handling and reporting

## Current Capabilities
1. Generate OAuth URLs for Twitter connection
2. Handle OAuth callbacks and token exchange
3. Store tokens securely in RDS
4. Emit events for successful/failed auth
5. Scale horizontally with ECS
6. Monitor via CloudWatch logs

## Next Steps
1. Test end-to-end OAuth flow with updated token storage
2. Implement token refresh mechanism
3. Add YouTube OAuth integration
4. Add TikTok OAuth integration
5. Implement social content ingestion
6. Set up auto-engage tasks

## Integration Points for Veri
1. Call `/connect/twitter` endpoint with user ID
2. Receive OAuth URL via `social.auth.url` event
3. Redirect user to OAuth URL
4. Handle callback at `/auth/twitter/callback`
5. Receive success/error via respective events
6. Query RDS for connected accounts/status

## Notes
- All components are cloud-native and scalable
- No Firebase dependency (direct event flow)
- Token storage is encrypted at rest
- Event-driven architecture allows easy extension
- Monitoring and logging in place
