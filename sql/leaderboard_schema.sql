-- Leaderboard configuration and data tables

-- Leaderboard definitions
CREATE TABLE leaderboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- maps to game_events.event_type
    score_field VARCHAR(255) NOT NULL, -- JSON path to score field in event payload
    score_type VARCHAR(50) NOT NULL,   -- 'highest', 'lowest', 'sum', 'average'
    score_formula TEXT,                -- Optional SQL formula for custom scoring
    time_period VARCHAR(50) NOT NULL,  -- 'daily', 'weekly', 'monthly', 'all_time'
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    is_rolling BOOLEAN DEFAULT false,
    max_entries_per_user INTEGER DEFAULT 1000,
    highest_scores_per_user INTEGER DEFAULT 1,
    required_metadata JSONB DEFAULT '[]'::jsonb, -- Array of required fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, name)
);

-- Current leaderboard entries (materialized and updated by consumer)
CREATE TABLE leaderboard_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leaderboard_id UUID NOT NULL REFERENCES leaderboards(id),
    player_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(255) NOT NULL,
    score NUMERIC NOT NULL,
    rank INTEGER NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    achieved_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(leaderboard_id, player_id, rank)
);

-- Historical leaderboard snapshots (for time periods)
CREATE TABLE leaderboard_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leaderboard_id UUID NOT NULL REFERENCES leaderboards(id),
    time_period VARCHAR(50) NOT NULL, -- 'daily', 'weekly', 'monthly'
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    entries JSONB NOT NULL, -- Array of ranked entries
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Example query to create a leaderboard
INSERT INTO leaderboards (
    game_id,
    name,
    event_type,
    score_field,
    score_type,
    time_period,
    start_date,
    end_date,
    is_rolling,
    required_metadata
) VALUES (
    'AssasinsCreed_Shadows',
    'Daily Kill Leader',
    'kill',
    'data.killStreak',
    'highest',
    'daily',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP + INTERVAL '30 days',
    true,
    '["weaponName", "isHeadshot"]'::jsonb
);

-- Example query to get current leaderboard
SELECT 
    rank,
    player_name,
    score,
    metadata,
    achieved_at
FROM leaderboard_entries
WHERE leaderboard_id = ? -- UUID of leaderboard
ORDER BY rank ASC
LIMIT 10;

-- Indexes for common queries
CREATE INDEX idx_leaderboard_entries_rank ON leaderboard_entries(leaderboard_id, rank);
CREATE INDEX idx_leaderboard_entries_score ON leaderboard_entries(leaderboard_id, score DESC);
CREATE INDEX idx_leaderboard_entries_player ON leaderboard_entries(leaderboard_id, player_id);
CREATE INDEX idx_leaderboard_history_period ON leaderboard_history(leaderboard_id, time_period, period_start);
