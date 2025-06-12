-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS leaderboard_history;
DROP TABLE IF EXISTS leaderboard_entries;
DROP TABLE IF EXISTS leaderboards;

-- Fix leaderboard tables
CREATE TABLE leaderboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    score_field VARCHAR(255) NOT NULL,
    score_type VARCHAR(50) NOT NULL,
    score_formula TEXT,
    time_period VARCHAR(50) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    is_rolling BOOLEAN DEFAULT false,
    max_entries_per_user INTEGER DEFAULT 1000,
    highest_scores_per_user INTEGER DEFAULT 1,
    required_metadata JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, name)
);

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

CREATE TABLE leaderboard_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leaderboard_id UUID NOT NULL REFERENCES leaderboards(id),
    time_period VARCHAR(50) NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    entries JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_leaderboard_entries_rank ON leaderboard_entries(leaderboard_id, rank);
CREATE INDEX idx_leaderboard_entries_score ON leaderboard_entries(leaderboard_id, score DESC);
CREATE INDEX idx_leaderboard_entries_player ON leaderboard_entries(leaderboard_id, player_id);
CREATE INDEX idx_leaderboard_history_period ON leaderboard_history(leaderboard_id, time_period, period_start);
