import { FirebaseEvent, GameEvent } from './types';

export function transformFirebaseEvent(event: FirebaseEvent): GameEvent {
  // Clean metadata by removing undefined values
  const cleanMetadata: Record<string, any> = {};
  if (event.metadata) {
    Object.entries(event.metadata).forEach(([key, value]) => {
      if (value !== undefined) {
        cleanMetadata[key] = value;
      }
    });
  }
  // Ensure score is a number
  const score = typeof event.score === 'string' ? parseFloat(event.score) : event.score;

  return {
    user_id: event.playerId,
    game_id: event.gameId,
    event_type: event.type,
    studio_id: event.studioId,
    timestamp: event.timestamp,
    payload: {
      leaderboard_id: event.leaderboardId,
      player_name: event.playerName,
      score: score,
      timeframe: event.timeframe,
      platform: cleanMetadata?.platform,
      sdk_version: cleanMetadata?.sdkVersion,
      metadata: {
        ...cleanMetadata,
        // Remove fields we've already mapped
        platform: undefined,
        sdkVersion: undefined
      }
    }
  };
}

export function validateEventType(type: string): boolean {
  return ['leaderboard_create', 'leaderboard_update', 'game_start', 'game_end', 'achievement', 
          'score_update', 'kill', 'death', 'level_up', 'quest_progress', 
          'item_acquire', 'custom', 'quest_create', 'tournament_create'].includes(type);
}
