# Integration Examples

## Basic Event Integration

### Node.js Example
```javascript
const axios = require('axios');

async function sendGameEvent(event) {
  try {
    const response = await axios.post('http://localhost:3001/events', {
      gameId: 'your_game_id',
      studioId: 'your_studio_id',
      playerId: 'player_123',
      playerName: 'CoolGamer',
      type: event.type,
      timestamp: new Date().toISOString(),
      metadata: {
        platform: 'windows',
        sdkVersion: '1.0.0',
        buildHash: 'release-1.2.3',
        apiKey: 'your_api_key',
        ...event.metadata
      }
    });
    
    console.log('Event sent successfully:', response.data);
    return response.data;
  } catch (error) {
    console.error('Failed to send event:', error.response?.data || error.message);
    throw error;
  }
}

// Example usage
sendGameEvent({
  type: 'kill',
  metadata: {
    weapon: 'sword',
    target: 'dragon',
    points: 100
  }
});
```

### Unity Example
```csharp
using UnityEngine;
using UnityEngine.Networking;
using System.Threading.Tasks;
using System.Text;
using System;

public class BrightMatterEvents : MonoBehaviour
{
    private const string API_URL = process.env.NODE_ENV === 'production'
    ? "https://api.brightmatter.gg/events"  // Production (coming soon)
    : "http://localhost:3001/events";       // Development
    private const string GAME_ID = "your_game_id";
    private const string STUDIO_ID = "your_studio_id";
    private const string API_KEY = "your_api_key";

    public async Task SendGameEvent(string eventType, object metadata)
    {
        var eventData = new
        {
            gameId = GAME_ID,
            studioId = STUDIO_ID,
            playerId = PlayerManager.Instance.CurrentPlayerId,
            playerName = PlayerManager.Instance.CurrentPlayerName,
            type = eventType,
            timestamp = DateTime.UtcNow.ToString("o"),
            metadata = new
            {
                platform = Application.platform.ToString(),
                sdkVersion = Application.version,
                buildHash = Application.buildGUID,
                apiKey = API_KEY,
                additionalData = metadata
            }
        };

        var json = JsonUtility.ToJson(eventData);
        var request = new UnityWebRequest(API_URL, "POST");
        byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
        request.uploadHandler = new UploadHandlerRaw(bodyRaw);
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");

        try
        {
            await request.SendWebRequest();
            if (request.result == UnityWebRequest.Result.Success)
            {
                Debug.Log("Event sent successfully");
            }
            else
            {
                Debug.LogError($"Failed to send event: {request.error}");
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"Error sending event: {e.Message}");
        }
    }
}

// Example usage
void OnEnemyKilled(string enemyType, int points)
{
    var metadata = new
    {
        enemy = enemyType,
        points = points,
        weapon = PlayerManager.Instance.CurrentWeapon
    };
    
    await SendGameEvent("kill", metadata);
}
```

### Unreal Engine Example
```cpp
#include "HttpModule.h"
#include "Json.h"
#include "JsonUtilities.h"

class BrightMatterEvents
{
public:
    static void SendGameEvent(const FString& EventType, const TSharedPtr<FJsonObject>& Metadata)
    {
        TSharedPtr<FJsonObject> EventData = MakeShared<FJsonObject>();
        EventData->SetStringField(TEXT("gameId"), TEXT("your_game_id"));
        EventData->SetStringField(TEXT("studioId"), TEXT("your_studio_id"));
        EventData->SetStringField(TEXT("playerId"), PlayerManager::Get()->GetCurrentPlayerId());
        EventData->SetStringField(TEXT("playerName"), PlayerManager::Get()->GetCurrentPlayerName());
        EventData->SetStringField(TEXT("type"), EventType);
        EventData->SetStringField(TEXT("timestamp"), FDateTime::UtcNow().ToIso8601());
        
        TSharedPtr<FJsonObject> MetadataObj = MakeShared<FJsonObject>();
        MetadataObj->SetStringField(TEXT("platform"), FPlatformProperties::IniPlatformName());
        MetadataObj->SetStringField(TEXT("sdkVersion"), FApp::GetBuildVersion());
        MetadataObj->SetStringField(TEXT("buildHash"), FApp::GetBuildVersion());
        MetadataObj->SetStringField(TEXT("apiKey"), TEXT("your_api_key"));
        
        // Merge additional metadata
        for (const auto& Entry : Metadata->Values)
        {
            MetadataObj->SetField(Entry.Key, Entry.Value);
        }
        
        EventData->SetObjectField(TEXT("metadata"), MetadataObj);

        FString JsonString;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonString);
        FJsonSerializer::Serialize(EventData.ToSharedRef(), Writer);

        TSharedRef<IHttpRequest> Request = FHttpModule::Get().CreateRequest();
        Request->SetURL(TEXT("http://localhost:3001/events"));
        Request->SetVerb(TEXT("POST"));
        Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
        Request->SetContentAsString(JsonString);
        
        Request->OnProcessRequestComplete().BindLambda(
            [](FHttpRequestPtr Request, FHttpResponsePtr Response, bool bSuccess)
            {
                if (bSuccess && Response.IsValid())
                {
                    UE_LOG(LogTemp, Log, TEXT("Event sent successfully"));
                }
                else
                {
                    UE_LOG(LogTemp, Error, TEXT("Failed to send event"));
                }
            });
            
        Request->ProcessRequest();
    }
};

// Example usage
void AGameMode::OnEnemyKilled(const FString& EnemyType, int32 Points)
{
    TSharedPtr<FJsonObject> Metadata = MakeShared<FJsonObject>();
    Metadata->SetStringField(TEXT("enemy"), EnemyType);
    Metadata->SetNumberField(TEXT("points"), Points);
    Metadata->SetStringField(TEXT("weapon"), PlayerManager::Get()->GetCurrentWeapon());
    
    BrightMatterEvents::SendGameEvent(TEXT("kill"), Metadata);
}
```

## Common Event Patterns

### Player Session Tracking
```javascript
// Start of game session
sendGameEvent({
  type: 'game_start',
  metadata: {
    session_id: 'session_123',
    game_mode: 'campaign',
    difficulty: 'normal',
    save_slot: 2
  }
});

// End of game session
sendGameEvent({
  type: 'game_end',
  metadata: {
    session_id: 'session_123',
    duration: 3600,
    levels_completed: 5,
    total_score: 15000
  }
});
```

### Achievement Progress
```javascript
// Progress update
sendGameEvent({
  type: 'achievement_progress',
  metadata: {
    achievement_id: 'master_archer',
    current_progress: 75,
    total_required: 100,
    description: 'Hit 100 targets with bow and arrow'
  }
});

// Achievement unlock
sendGameEvent({
  type: 'achievement_unlocked',
  metadata: {
    achievement_id: 'master_archer',
    unlock_time: '2025-06-09T20:30:53Z',
    difficulty: 'normal',
    rewards: ['special_bow', 'archer_title']
  }
});
```

### Leaderboard Updates
```javascript
// Score update
sendGameEvent({
  type: 'leaderboard_update',
  metadata: {
    leaderboard_id: 'weekly_high_scores',
    score: 15000,
    timeframe: 'weekly',
    mode: 'arcade',
    details: {
      kills: 50,
      accuracy: 0.85,
      time_alive: 300
    }
  }
});
```

## Error Handling

Always implement proper error handling and retry logic:

```javascript
async function sendGameEventWithRetry(event, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await sendGameEvent(event);
    } catch (error) {
      if (attempt === maxRetries) throw error;
      
      const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
      console.log(`Retry attempt ${attempt} after ${delay}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

## Event Batching

For high-frequency events, consider batching:

```javascript
class EventBatcher {
  constructor(batchSize = 10, flushInterval = 1000) {
    this.events = [];
    this.batchSize = batchSize;
    this.flushInterval = flushInterval;
    this.timer = setInterval(() => this.flush(), flushInterval);
  }

  addEvent(event) {
    this.events.push(event);
    if (this.events.length >= this.batchSize) {
      this.flush();
    }
  }

  async flush() {
    if (this.events.length === 0) return;
    
    const batch = this.events.splice(0, this.batchSize);
    try {
      await sendBatchedEvents(batch);
    } catch (error) {
      console.error('Failed to send batch:', error);
      // Re-add failed events
      this.events.unshift(...batch);
    }
  }

  destroy() {
    clearInterval(this.timer);
  }
}
```
