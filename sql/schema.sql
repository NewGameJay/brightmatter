-- Core tables for game events

-- Raw events table
CREATE TABLE game_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    player_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    platform VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Player stats (aggregated)
CREATE TABLE player_stats (
    player_id VARCHAR(255) NOT NULL,
    game_id VARCHAR(255) NOT NULL,
    total_kills INTEGER DEFAULT 0,
    total_deaths INTEGER DEFAULT 0,
    total_damage_dealt BIGINT DEFAULT 0,
    total_damage_taken BIGINT DEFAULT 0,
    total_healing BIGINT DEFAULT 0,
    boss_kills INTEGER DEFAULT 0,
    levels_completed INTEGER DEFAULT 0,
    playtime_seconds BIGINT DEFAULT 0,
    last_session_id VARCHAR(255),
    last_seen_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (player_id, game_id)
);

-- Session tracking
CREATE TABLE game_sessions (
    session_id VARCHAR(255) NOT NULL,
    game_id VARCHAR(255) NOT NULL,
    player_id VARCHAR(255) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    platform VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL,
    build_version VARCHAR(50),
    PRIMARY KEY (session_id)
);

-- Level progression
CREATE TABLE level_progress (
    player_id VARCHAR(255) NOT NULL,
    game_id VARCHAR(255) NOT NULL,
    level_id VARCHAR(255) NOT NULL,
    attempts INTEGER DEFAULT 0,
    completions INTEGER DEFAULT 0,
    best_time_seconds INTEGER,
    best_score INTEGER,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (player_id, game_id, level_id)
);

-- Indexes for common queries
CREATE INDEX idx_game_events_game_type ON game_events(game_id, event_type);
CREATE INDEX idx_game_events_player ON game_events(player_id);
CREATE INDEX idx_game_events_timestamp ON game_events(timestamp);
CREATE INDEX idx_game_events_session ON game_events(session_id);

-- Composite indexes for leaderboards
CREATE INDEX idx_player_stats_kills ON player_stats(game_id, total_kills DESC);
CREATE INDEX idx_player_stats_damage ON player_stats(game_id, total_damage_dealt DESC);
CREATE INDEX idx_level_progress_time ON level_progress(game_id, level_id, best_time_seconds ASC);

-- Example queries for frontend

-- Get top 10 players by kills for a game
-- SELECT player_id, player_name, total_kills 
-- FROM player_stats 
-- WHERE game_id = ? 
-- ORDER BY total_kills DESC 
-- LIMIT 10;

-- Get player's level progress
-- SELECT level_id, attempts, completions, best_time_seconds, best_score
-- FROM level_progress
-- WHERE game_id = ? AND player_id = ?;

-- Get recent game sessions
-- SELECT s.*, p.total_kills, p.total_deaths
-- FROM game_sessions s
-- JOIN player_stats p ON s.player_id = p.player_id AND s.game_id = p.game_id
-- WHERE s.game_id = ?
-- ORDER BY start_time DESC
-- LIMIT 20;
