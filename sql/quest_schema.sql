-- Quest configuration and data tables

-- Quest definitions
CREATE TABLE quests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    objectives JSONB NOT NULL,  -- Array of objective objects
    rewards JSONB NOT NULL,     -- Object containing rewards
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    requirements JSONB,         -- Optional requirements object
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, name)
);

-- Quest progress tracking
CREATE TABLE quest_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_id UUID NOT NULL REFERENCES quests(id),
    player_id VARCHAR(255) NOT NULL,
    objectives_progress JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Array of objective progress
    status VARCHAR(50) NOT NULL DEFAULT 'in_progress',       -- in_progress, completed, failed
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quest_id, player_id)
);

-- Example quest creation
INSERT INTO quests (
    game_id,
    name,
    description,
    objectives,
    rewards
) VALUES (
    'brightmatter-test',
    'Dragon Slayer',
    'Defeat the mighty dragon and collect its scales',
    '[
        {"type": "kill", "target": "dragon", "count": 1},
        {"type": "collect", "target": "dragon_scale", "count": 5}
    ]'::jsonb,
    '{
        "experience": 1000,
        "items": ["dragon_sword", "dragon_shield"]
    }'::jsonb
);

-- Indexes for common queries
CREATE INDEX idx_quests_game ON quests(game_id);
CREATE INDEX idx_quest_progress_player ON quest_progress(player_id);
CREATE INDEX idx_quest_progress_status ON quest_progress(quest_id, status);
