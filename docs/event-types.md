# Event Types

This document lists all supported event types in the BrightMatter platform. Each event type has a specific purpose and recommended payload structure.

## Core Events

### Game Session Events
- `game_start` - Player starts a game session
- `game_end` - Player ends a game session
- `checkpoint_reached` - Player reaches a checkpoint
- `level_start` - Player starts a level
- `level_complete` - Player completes a level
- `level_failed` - Player fails a level

### Combat Events
- `kill` - Player kills an enemy/opponent
- `death` - Player dies
- `damage_dealt` - Player deals damage
- `damage_taken` - Player takes damage
- `heal` - Player heals
- `boss_encounter` - Player encounters a boss
- `boss_kill` - Player defeats a boss
- `weapon_fired` - Player fires a weapon
- `ability_used` - Player uses an ability
- `combo_achieved` - Player achieves a combo

### Progression Events
- `level_up` - Player levels up
- `experience_gained` - Player gains experience points
- `skill_unlocked` - Player unlocks a skill
- `skill_upgraded` - Player upgrades a skill
- `achievement_progress` - Progress towards an achievement
- `achievement_unlocked` - Player unlocks an achievement
- `quest_accepted` - Player accepts a quest
- `quest_progress` - Progress in a quest
- `quest_completed` - Player completes a quest
- `quest_failed` - Player fails a quest
- `objective_complete` - Player completes an objective

### Economy Events
- `currency_earned` - Player earns currency
- `currency_spent` - Player spends currency
- `item_acquired` - Player acquires an item
- `item_upgraded` - Player upgrades an item
- `item_sold` - Player sells an item
- `item_crafted` - Player crafts an item
- `resource_gathered` - Player gathers resources
- `store_opened` - Player opens the store
- `purchase_initiated` - Player initiates a purchase
- `purchase_completed` - Player completes a purchase

### Social Events
- `party_joined` - Player joins a party
- `party_left` - Player leaves a party
- `guild_joined` - Player joins a guild
- `guild_left` - Player leaves a guild
- `friend_added` - Player adds a friend
- `message_sent` - Player sends a message
- `trade_initiated` - Player initiates a trade
- `trade_completed` - Player completes a trade
- `gift_sent` - Player sends a gift
- `gift_received` - Player receives a gift

### Competition Events
- `match_started` - Competitive match starts
- `match_ended` - Competitive match ends
- `round_start` - Round starts
- `round_end` - Round ends
- `score_update` - Player's score changes
- `rank_changed` - Player's rank changes
- `leaderboard_update` - Leaderboard position update
- `tournament_joined` - Player joins a tournament
- `tournament_eliminated` - Player is eliminated from tournament
- `tournament_victory` - Player wins a tournament

### Character Events
- `character_created` - Player creates a character
- `character_deleted` - Player deletes a character
- `class_changed` - Player changes character class
- `appearance_changed` - Player changes character appearance
- `loadout_changed` - Player changes equipment loadout
- `stats_allocated` - Player allocates stat points

### World Events
- `area_discovered` - Player discovers a new area
- `fast_travel` - Player uses fast travel
- `location_reached` - Player reaches a specific location
- `collectible_found` - Player finds a collectible
- `secret_discovered` - Player discovers a secret
- `treasure_opened` - Player opens a treasure chest
- `npc_interaction` - Player interacts with an NPC
- `dialogue_choice` - Player makes a dialogue choice

### Performance Events
- `fps_drop` - Game experiences FPS drop
- `latency_spike` - Network latency spike detected
- `crash_report` - Game crash report
- `error_log` - Game error log
- `client_info` - Client system information

### Custom Events
- `custom` - Custom event type (requires detailed metadata)

## Event Payload Examples

### Combat Event Example
```json
{
  "type": "kill",
  "metadata": {
    "weapon": "plasma_rifle",
    "target_type": "elite_enemy",
    "damage_dealt": 150,
    "distance": 45.5,
    "headshot": true,
    "weapon_level": 3,
    "combat_multiplier": 2.5
  }
}
```

### Progression Event Example
```json
{
  "type": "level_up",
  "metadata": {
    "new_level": 10,
    "experience_gained": 1500,
    "total_experience": 15000,
    "unlocked_abilities": ["double_jump", "wall_run"],
    "stat_increases": {
      "strength": 2,
      "agility": 1,
      "endurance": 1
    }
  }
}
```

### Economy Event Example
```json
{
  "type": "item_acquired",
  "metadata": {
    "item_id": "legendary_sword_123",
    "item_name": "Thunderfury",
    "rarity": "legendary",
    "source": "boss_drop",
    "attributes": {
      "damage": 150,
      "element": "lightning",
      "durability": 100
    },
    "inventory_slot": "weapon_main"
  }
}
```

## Best Practices

1. Always include relevant metadata for each event type
2. Use consistent naming conventions for similar events
3. Include timestamps for all events
4. Group related events (e.g., start/end pairs)
5. Include context in event metadata
6. Use appropriate data types for values
7. Keep payload sizes reasonable

## Rate Limits

- Standard Tier: 100 events per second
- Premium Tier: 1000 events per second
- Enterprise Tier: Custom limits

## Event Retention

Events are retained according to your service tier:
- Standard Tier: 30 days
- Premium Tier: 90 days
- Enterprise Tier: Custom retention periods
