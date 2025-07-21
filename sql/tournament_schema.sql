-- Tournament configuration and data tables

-- Tournament definitions
CREATE TABLE tournaments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    requirements JSONB DEFAULT '{}'::jsonb,  -- Optional requirements
    rewards JSONB NOT NULL,                  -- Required rewards structure
    rules JSONB DEFAULT '[]'::jsonb,         -- Optional rules array
    max_participants INTEGER,                 -- Optional max participants
    status VARCHAR(50) DEFAULT 'upcoming',    -- upcoming, active, completed, cancelled
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, name)
);

-- Tournament participants
CREATE TABLE tournament_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournaments(id),
    player_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(255) NOT NULL,
    score NUMERIC DEFAULT 0,
    rank INTEGER,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, player_id)
);

-- Tournament history (for completed tournaments)
CREATE TABLE tournament_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournaments(id),
    winners JSONB NOT NULL,  -- Array of winning players with rewards
    total_participants INTEGER NOT NULL,
    final_scores JSONB NOT NULL,  -- Complete leaderboard data
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Example tournament creation
INSERT INTO tournaments (
    game_id,
    name,
    description,
    start_date,
    end_date,
    requirements,
    rewards,
    rules,
    max_participants
) VALUES (
    'brightmatter-test',
    'Weekly Challenge',
    'Get the highest score in a week',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP + INTERVAL '7 days',
    '{"minLevel": 10, "maxLevel": 50}'::jsonb,
    '{"first": 1000, "second": 500, "third": 250}'::jsonb,
    '["No cheating", "One entry per player"]'::jsonb,
    100
);

-- Indexes for common queries
CREATE INDEX idx_tournaments_game ON tournaments(game_id);
CREATE INDEX idx_tournaments_status ON tournaments(status);
CREATE INDEX idx_tournament_participants_score ON tournament_participants(tournament_id, score DESC);
CREATE INDEX idx_tournament_participants_rank ON tournament_participants(tournament_id, rank);
CREATE INDEX idx_tournament_history_completed ON tournament_history(completed_at DESC);
