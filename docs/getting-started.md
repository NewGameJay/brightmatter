# Getting Started with BrightMatter

## Overview

BrightMatter provides a powerful event tracking system for games. This guide will help you get started with integrating BrightMatter into your game.

## Prerequisites

1. A BrightMatter account
2. Your game credentials:
   - Game ID
   - Studio ID
   - API Key

## Integration Steps

### 1. Account Setup

1. Sign up at [BrightMatter Dashboard](https://dashboard.brightmatter.gg)
2. Create a new game in your studio
3. Get your credentials from the game settings page

### 2. Basic Integration

Choose your preferred integration method:

1. **Direct API Integration**
   - Use our REST API directly
   - Good for custom implementations
   - See [API Reference](./api-reference.md)

2. **SDK Integration**
   - Use our official SDKs
   - Available for Unity, Unreal, and more
   - See [SDK Integration](./sdk-integration.md)

### 3. Testing Your Integration

1. Use test credentials in development
2. Send test events using our examples
3. View events in real-time in the dashboard
4. Validate event processing

## Quick Start Example

```javascript
const event = {
  gameId: "your_game_id",
  studioId: "your_studio_id",
  playerId: "player_123",
  playerName: "TestPlayer",
  type: "game_start",
  timestamp: new Date().toISOString(),
  metadata: {
    platform: "windows",
    sdkVersion: "1.0.0",
    buildHash: "release-1.2.3",
    apiKey: "your_api_key",
    gameMode: "campaign",
    difficulty: "normal"
  }
};

// Send the event
fetch('http://localhost:3001/events', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(event)
})
.then(response => response.json())
.then(data => console.log('Success:', data))
.catch(error => console.error('Error:', error));
```

## Next Steps

1. Review the [Event Types](./event-types.md) documentation
2. Implement comprehensive event tracking
3. Set up real-time dashboards
4. Configure alerts and notifications
5. Explore advanced features:
   - Custom events
   - Event batching
   - Rate limiting strategies
   - Error handling

## Support

- Documentation: [docs.brightmatter.gg](https://docs.brightmatter.gg)
- Support Email: support@brightmatter.gg
- Discord: [BrightMatter Discord](https://discord.gg/brightmatter)
- GitHub: [BrightMatter Examples](https://github.com/brightmatter/examples)
