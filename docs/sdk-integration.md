# SDK Integration Guide

## Available SDKs

BrightMatter provides official SDKs for major game engines and platforms:

- Unity SDK
- Unreal Engine SDK
- JavaScript SDK
- C++ SDK
- Java SDK
- Python SDK

## Unity SDK

### Installation

1. Open your Unity project
2. Import the BrightMatter SDK package
3. Add the BrightMatter prefab to your scene

### Basic Setup

```csharp
using BrightMatter;

public class BrightMatterManager : MonoBehaviour
{
    void Start()
    {
        BrightMatter.Initialize(new BrightMatterConfig
        {
            GameId = "your_game_id",
            StudioId = "your_studio_id",
            ApiKey = "your_api_key",
            Environment = BrightMatterEnvironment.Production
        });
    }
}
```

### Sending Events

```csharp
// Simple event
BrightMatter.SendEvent("kill", new Dictionary<string, object>
{
    { "weapon", "sword" },
    { "target", "dragon" },
    { "damage", 100 }
});

// With callback
BrightMatter.SendEvent("level_complete", new Dictionary<string, object>
{
    { "level_id", "dungeon_1" },
    { "time_taken", 300 },
    { "score", 1500 }
}, (success, response) =>
{
    if (success)
    {
        Debug.Log("Event sent successfully");
    }
    else
    {
        Debug.LogError("Failed to send event: " + response);
    }
});
```

## Unreal Engine SDK

### Installation

1. Add the BrightMatter plugin to your project
2. Enable the plugin in your project settings
3. Configure your credentials

### Basic Setup

```cpp
#include "BrightMatterSubsystem.h"

void AGameModeBase::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
    Super::InitGame(MapName, Options, ErrorMessage);
    
    auto* BrightMatter = GEngine->GetWorld()->GetSubsystem<UBrightMatterSubsystem>();
    BrightMatter->Initialize(FBrightMatterConfig{
        TEXT("your_game_id"),
        TEXT("your_studio_id"),
        TEXT("your_api_key"),
        EBrightMatterEnvironment::Production
    });
}
```

### Sending Events

```cpp
// Simple event
FBrightMatterEvent Event;
Event.Type = TEXT("kill");
Event.Metadata.Add(TEXT("weapon"), TEXT("sword"));
Event.Metadata.Add(TEXT("target"), TEXT("dragon"));
Event.Metadata.Add(TEXT("damage"), 100);

UBrightMatterSubsystem::Get()->SendEvent(Event);

// With callback
UBrightMatterSubsystem::Get()->SendEvent(Event,
    FBrightMatterCallback::CreateLambda([](bool bSuccess, const FString& Response)
    {
        if (bSuccess)
        {
            UE_LOG(LogTemp, Log, TEXT("Event sent successfully"));
        }
        else
        {
            UE_LOG(LogTemp, Error, TEXT("Failed to send event: %s"), *Response);
        }
    })
);
```

## JavaScript SDK

### Installation

```bash
npm install @brightmatter/sdk
# or
yarn add @brightmatter/sdk
```

### Basic Setup

```javascript
import { BrightMatter } from '@brightmatter/sdk';

const brightMatter = new BrightMatter({
    gameId: 'your_game_id',
    studioId: 'your_studio_id',
    apiKey: 'your_api_key',
    environment: 'production'
});
```

### Sending Events

```javascript
// Simple event
await brightMatter.sendEvent('kill', {
    weapon: 'sword',
    target: 'dragon',
    damage: 100
});

// With error handling
try {
    await brightMatter.sendEvent('level_complete', {
        level_id: 'dungeon_1',
        time_taken: 300,
        score: 1500
    });
    console.log('Event sent successfully');
} catch (error) {
    console.error('Failed to send event:', error);
}
```

## Best Practices

### 1. Event Batching

For high-frequency events, use batching:

```javascript
brightMatter.enableBatching({
    maxSize: 10,
    maxWait: 1000
});

// Events will be automatically batched
brightMatter.sendEvent(...);
```

### 2. Offline Support

Handle offline scenarios:

```javascript
brightMatter.enableOfflineSupport({
    maxStorageSize: 1000,
    persistenceKey: 'brightmatter_events'
});
```

### 3. Error Handling

Implement proper error handling:

```javascript
brightMatter.onError((error) => {
    console.error('BrightMatter error:', error);
    // Implement your error handling logic
});
```

### 4. Debug Mode

Enable debug mode during development:

```javascript
brightMatter.setDebugMode(true);
```

### 5. Event Validation

Validate events before sending:

```javascript
brightMatter.validateEvents = true;
```

## Advanced Features

### Custom Event Transformations

```javascript
brightMatter.addEventTransform((event) => {
    // Add custom fields
    event.metadata.client_timestamp = Date.now();
    return event;
});
```

### Rate Limiting

```javascript
brightMatter.setRateLimit({
    eventsPerSecond: 100,
    burstSize: 1000
});
```

### Automatic Retries

```javascript
brightMatter.setRetryConfig({
    maxRetries: 3,
    backoffMultiplier: 2,
    initialDelay: 1000
});
```

## Testing

### Test Mode

```javascript
brightMatter.setTestMode(true);
```

### Event Validation

```javascript
brightMatter.validateEvent({
    type: 'kill',
    metadata: {
        weapon: 'sword'
    }
}).then(isValid => {
    console.log('Event is valid:', isValid);
});
```

## Troubleshooting

1. Check SDK initialization
2. Verify credentials
3. Monitor network requests
4. Check event validation
5. Review rate limits
6. Inspect error callbacks

## Support

For SDK support:
- Documentation: docs.brightmatter.gg/sdk
- GitHub Issues: github.com/brightmatter/sdk/issues
- Discord: discord.gg/brightmatter
- Email: sdk-support@brightmatter.gg
