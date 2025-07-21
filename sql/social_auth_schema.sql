-- Social authentication and account tables

-- Social accounts table for storing OAuth tokens and platform data
CREATE TABLE social_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,  -- Firebase UID
    platform VARCHAR(50) NOT NULL,   -- 'twitter', 'youtube', etc.
    external_user_id VARCHAR(255),   -- Platform's user ID
    username VARCHAR(255),           -- Platform username/handle
    access_token TEXT NOT NULL,      -- OAuth access token
    refresh_token TEXT,             -- OAuth refresh token (if available)
    token_expires_at TIMESTAMP WITH TIME ZONE,
    scopes TEXT[] NOT NULL,         -- Array of granted OAuth scopes
    metadata JSONB DEFAULT '{}'::jsonb,  -- Additional platform-specific data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, platform)
);

-- Create indexes for common queries
CREATE INDEX idx_social_accounts_user ON social_accounts(user_id);
CREATE INDEX idx_social_accounts_platform ON social_accounts(platform, external_user_id);
CREATE INDEX idx_social_accounts_expires ON social_accounts(token_expires_at) WHERE token_expires_at IS NOT NULL;

-- Example query to find accounts needing token refresh
-- SELECT id, user_id, platform, refresh_token 
-- FROM social_accounts 
-- WHERE token_expires_at < NOW() + INTERVAL '1 day' 
-- AND refresh_token IS NOT NULL;
