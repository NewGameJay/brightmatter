# BrightMatter Event Payload Templates

This document provides template payloads for each supported event type. Game developers should follow these structures to ensure proper data formatting and frontend display.

## Common Fields
All events require these base fields:
```json
{
  "gameId": "your_game_id",
  "type": "event_type",
  "data": {
    "playerId": "unique_player_id",
    "playerName": "player_display_name",
    "sessionId": "unique_session_id",
    "timestamp": "2025-06-11T12:39:11Z",
    "platform": "PC|MOBILE|CONSOLE",
    "region": "NA|EU|ASIA|etc"
  }
}
```

## Game Session Events

### game_start
```json
{
  "type": "game_start",
  "data": {
    "buildVersion": "1.2.3",
    "deviceInfo": "Windows 10",
    "clientSettings": {
      "graphics": "high",
      "resolution": "1920x1080"
    }
  }
}
```

### game_end
```json
{
  "type": "game_end",
  "data": {
    "duration": 3600,
    "reason": "quit|disconnect|completed",
    "totalScore": 1500
  }
}
```

### checkpoint_reached
```json
{
  "type": "checkpoint_reached",
  "data": {
    "checkpointId": "checkpoint_123",
    "checkpointName": "Castle Gate",
    "levelId": "level_1",
    "timeToReach": 300
  }
}
```

### level_start
```json
{
  "type": "level_start",
  "data": {
    "levelId": "level_123",
    "levelName": "The Dark Forest",
    "difficulty": "normal|hard|nightmare",
    "previousAttempts": 2
  }
}
```

### level_complete
```json
{
  "type": "level_complete",
  "data": {
    "levelId": "level_123",
    "levelName": "The Dark Forest",
    "timeToComplete": 600,
    "score": 1000,
    "starsEarned": 3,
    "collectiblesFound": 10,
    "totalCollectibles": 15
  }
}
```

### level_failed
```json
{
  "type": "level_failed",
  "data": {
    "levelId": "level_123",
    "levelName": "The Dark Forest",
    "timeSpent": 300,
    "failReason": "death|timeout|objective_failed",
    "progressPercent": 75
  }
}
```

## Combat Events

### kill
```json
{
  "type": "kill",
  "data": {
    "targetId": "enemy_123",
    "targetType": "grunt|elite|boss",
    "weaponId": "weapon_123",
    "weaponName": "Excalibur",
    "damageDealt": 100,
    "killDistance": 50,
    "isHeadshot": false,
    "isMultiKill": false,
    "killStreak": 3
  }
}
```

### death
```json
{
  "type": "death",
  "data": {
    "killerId": "enemy_or_player_id",
    "killerType": "enemy|environment|player",
    "causeOfDeath": "weapon|fall|poison|etc",
    "locationX": 100,
    "locationY": 200,
    "locationZ": 50,
    "survivalTime": 300
  }
}
```

### damage_dealt
```json
{
  "type": "damage_dealt",
  "data": {
    "targetId": "enemy_123",
    "targetType": "grunt|elite|boss",
    "weaponId": "weapon_123",
    "weaponName": "Excalibur",
    "damage": 50,
    "isCritical": true,
    "hitLocation": "head|body|limb"
  }
}
```

### damage_taken
```json
{
  "type": "damage_taken",
  "data": {
    "attackerId": "enemy_123",
    "attackerType": "grunt|elite|boss",
    "damageType": "physical|fire|poison",
    "damage": 25,
    "remainingHealth": 75,
    "wasBlocked": false,
    "wasDodged": false
  }
}
```

### heal
```json
{
  "type": "heal",
  "data": {
    "healAmount": 50,
    "sourceId": "item_123",
    "sourceName": "Health Potion",
    "healType": "instant|overtime",
    "previousHealth": 50,
    "newHealth": 100
  }
}
```

### boss_encounter
```json
{
  "type": "boss_encounter",
  "data": {
    "bossId": "boss_123",
    "bossName": "Dragon King",
    "bossLevel": 50,
    "playerLevel": 45,
    "isFirstEncounter": true,
    "partySize": 1
  }
}
```

### boss_kill
```json
{
  "type": "boss_kill",
  "data": {
    "bossId": "boss_123",
    "bossName": "Dragon King",
    "timeToKill": 300,
    "damageDealt": 5000,
    "damageTaken": 2000,
    "attemptNumber": 3,
    "partySize": 1,
    "specialAchievements": ["no_damage", "speed_kill"]
  }
}
```

### weapon_fired
```json
{
  "type": "weapon_fired",
  "data": {
    "weaponId": "weapon_123",
    "weaponName": "Plasma Rifle",
    "ammoType": "plasma",
    "ammoUsed": 1,
    "ammoRemaining": 29,
    "isADS": true,
    "accuracy": 95
  }
}
```

## Frontend Display
These structured payloads enable the following frontend features:
- Leaderboards by kills, damage, boss kills
- Quest tracking for specific achievements
- Tournament progression tracking
- Player performance analytics
- Team/squad performance metrics

## Validation
The BrightMatter API will validate:
1. All required base fields are present
2. Event type is supported
3. Data fields match the expected structure
4. Values are within valid ranges

## Best Practices
1. Always include all relevant fields, even if optional
2. Use consistent IDs across related events
3. Include descriptive names along with IDs
4. Use UTC timestamps
5. Follow the exact field names and types shown in templates
