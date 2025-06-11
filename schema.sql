-- Core tables for BrightMatter

-- Game Events table
CREATE TABLE game_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL, -- Firebase UID
    game_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    payload JSONB NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster querying of game events
CREATE INDEX idx_game_events_user ON game_events(user_id, game_id, timestamp);

-- Social Posts table
CREATE TABLE social_posts (
    post_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR NOT NULL,
    creator_id VARCHAR NOT NULL, -- Firebase UID
    external_post_id VARCHAR NOT NULL,
    post_url TEXT NOT NULL,
    content_text TEXT,
    raw_metrics JSONB NOT NULL,
    campaign_id UUID,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, external_post_id)
);

-- Create index for creator posts
CREATE INDEX idx_social_posts_creator ON social_posts(creator_id, timestamp);

-- Campaigns table
CREATE TABLE campaigns (
    campaign_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    studio_id VARCHAR NOT NULL, -- Firebase UID
    title VARCHAR NOT NULL,
    description TEXT,
    requirements JSONB NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Campaign Assignments table
CREATE TABLE campaign_assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id),
    creator_id VARCHAR NOT NULL, -- Firebase UID
    status VARCHAR NOT NULL DEFAULT 'pending',
    tasks_completed JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, creator_id)
);

-- Tournaments table
CREATE TABLE tournaments (
    tournament_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    rules JSONB NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tournament Scores table
CREATE TABLE tournament_scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournaments(tournament_id),
    user_id VARCHAR NOT NULL, -- Firebase UID
    score NUMERIC NOT NULL DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, user_id)
);

-- Quests table
CREATE TABLE quests (
    quest_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT,
    requirements JSONB NOT NULL,
    rewards JSONB,
    start_date TIMESTAMP WITH TIME ZONE,
    end_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Quest Progress table
CREATE TABLE quest_progress (
    progress_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_id UUID NOT NULL REFERENCES quests(quest_id),
    user_id VARCHAR NOT NULL, -- Firebase UID
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed BOOLEAN NOT NULL DEFAULT false,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(quest_id, user_id)
);

-- VeriScores table (for storing calculated scores)
CREATE TABLE veri_scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id VARCHAR NOT NULL, -- Firebase UID
    score NUMERIC NOT NULL,
    metrics JSONB NOT NULL,
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(creator_id, calculated_at)
);

-- Formula Configurations table (for marketers to adjust scoring)
CREATE TABLE formula_configs (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL,
    description TEXT,
    formula JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT false,
    created_by VARCHAR NOT NULL, -- Firebase UID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX idx_campaign_dates ON campaigns(start_date, end_date);
CREATE INDEX idx_tournament_dates ON tournaments(start_date, end_date);
CREATE INDEX idx_quest_status ON quests(status, game_id);
CREATE INDEX idx_veri_scores_latest ON veri_scores(creator_id, calculated_at DESC);
