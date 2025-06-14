// Firebase Event Structure
export interface FirebaseEvent {
  leaderboardId?: string;
  gameId: string;
  playerId: string;
  playerName: string;
  score?: number | string;
  timeframe?: string;
  timestamp: string;
  type: string;
  metadata: {
    platform: string;
    sdkVersion: string;
    buildHash: string;
    apiKey: string;
    [key: string]: any;
  };
  studioId: string;
}

// Normalized Event Structure for PostgreSQL
export interface GameEvent {
  event_id?: string;      // UUID, generated if not provided
  user_id: string;        // Maps to playerId
  game_id: string;        // Maps to gameId
  event_type: string;     // Maps to type
  payload: {
    leaderboard_id?: string;
    player_name?: string;
    score?: number;
    timeframe?: string;
    platform?: string;
    sdk_version?: string;
    metadata?: Record<string, any>;
  };
  timestamp: string;      // ISO timestamp
  studio_id: string;      // Maps to studioId
}

// Event Types
export const EVENT_TYPES = [
  // Game Session Events
  'game_start',
  'game_end',
  'checkpoint_reached',
  'level_start',
  'level_complete',
  'level_failed',

  // Combat Events
  'kill',
  'death',
  'damage_dealt',
  'damage_taken',
  'heal',
  'boss_encounter',
  'boss_kill',
  'weapon_fired',
  'ability_used',
  'combo_achieved',

  // Progression Events
  'level_up',
  'experience_gained',
  'skill_unlocked',
  'skill_upgraded',
  'achievement_progress',
  'achievement_unlocked',
  'quest_accepted',
  'quest_progress',
  'quest_completed',
  'quest_failed',
  'objective_complete',

  // Economy Events
  'currency_earned',
  'currency_spent',
  'item_acquired',
  'item_upgraded',
  'item_sold',
  'item_crafted',
  'resource_gathered',
  'store_opened',
  'purchase_initiated',
  'purchase_completed',

  // Social Events
  'party_joined',
  'party_left',
  'guild_joined',
  'guild_left',
  'friend_added',
  'message_sent',
  'trade_initiated',
  'trade_completed',
  'gift_sent',
  'gift_received',

  // Competition Events
  'match_started',
  'match_ended',
  'round_start',
  'round_end',
  'score_update',
  'rank_changed',
  'leaderboard_update',
  'tournament_joined',
  'tournament_eliminated',
  'tournament_victory',

  // Character Events
  'character_created',
  'character_deleted',
  'class_changed',
  'appearance_changed',
  'loadout_changed',
  'stats_allocated',

  // World Events
  'area_discovered',
  'fast_travel',
  'location_reached',
  'collectible_found',
  'secret_discovered',
  'treasure_opened',
  'npc_interaction',
  'dialogue_choice',

  // Performance Events
  'fps_drop',
  'latency_spike',
  'crash_report',
  'error_log',
  'client_info',

  // Custom Events
  'custom'
] as const;

export type GameEventType = typeof EVENT_TYPES[number];
