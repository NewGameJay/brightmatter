-- BrightMatter Shared Database Schema (Supabase/Postgres)
--
-- All four platforms (MH1HQ, MH-OS, mh1-skills, Jarvis) write events
-- to the shared 'events' table. BrightMatter pulls on a cron schedule,
-- processes through the learning pipeline, and writes guidance back to
-- 'guidance_cache'. Each platform reads guidance before execution.

-- ── Events (write path) ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source TEXT NOT NULL,                         -- "mh-os", "mh1-hq", "mh1-skills", "jarvis"
  event_type TEXT NOT NULL,                     -- "signal", "skill_completed", "plan_completed",
                                                -- "human_feedback", "expert_override"
  skill_name TEXT,
  client_id TEXT NOT NULL,
  domain TEXT DEFAULT 'generic',
  result JSONB,
  metrics JSONB,
  context JSONB,                                -- includes channel_context
  channel_context JSONB,                        -- structured ChannelContext
  created_at TIMESTAMPTZ DEFAULT now(),
  processed_by_bm BOOLEAN DEFAULT false
);

-- ── Predictions (tracking) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS predictions (
  tracking_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  skill_name TEXT NOT NULL,
  client_id TEXT NOT NULL,
  domain TEXT DEFAULT 'generic',
  expected_signal FLOAT,
  expected_baseline FLOAT,
  confidence FLOAT DEFAULT 0.5,
  guidance JSONB,
  channel_context JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ── Outcomes (resolution) ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS outcomes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  tracking_id TEXT REFERENCES predictions(tracking_id),
  source TEXT NOT NULL,
  client_id TEXT NOT NULL,
  outcome_type TEXT NOT NULL,                   -- "24h_checkpoint", "7d_checkpoint", "immediate"
  observed_signal FLOAT,
  goal_completed BOOLEAN,
  business_impact FLOAT,
  feedback JSONB,
  external_context JSONB,                       -- seasonality, anomaly flags, platform issues
  measured_at TIMESTAMPTZ DEFAULT now()
);

-- ── Guidance Cache (read path) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS guidance_cache (
  skill_name TEXT NOT NULL,
  client_id TEXT NOT NULL,
  domain TEXT DEFAULT 'generic',
  parameters JSONB,
  confidence FLOAT DEFAULT 0.5,
  expected_value FLOAT,
  is_exploration BOOLEAN DEFAULT true,
  patterns_used TEXT[],
  predicted_outcome FLOAT,
  predicted_baseline FLOAT,
  pattern_expected_value FLOAT,
  channel_context JSONB,
  blend_weights JSONB,                          -- {"client": 0.15, "segment": 0.55, "universal": 0.30}
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (skill_name, client_id)
);

-- ── Patterns (mirror of Firebase semantic patterns) ────────────────

CREATE TABLE IF NOT EXISTS patterns (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  domain TEXT NOT NULL,
  skill_name TEXT,
  client_id TEXT,
  pattern_level TEXT,                           -- "universal", "segment", "client"
  description TEXT,
  confidence FLOAT,
  evidence_count INT DEFAULT 0,
  parameters JSONB,
  condition JSONB,
  expected_trajectory JSONB,
  expected_value FLOAT,
  recent_accuracy FLOAT DEFAULT 0.5,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_events_unprocessed
  ON events(processed_by_bm, created_at) WHERE NOT processed_by_bm;

CREATE INDEX IF NOT EXISTS idx_events_client
  ON events(client_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_events_source_type
  ON events(source, event_type);

CREATE INDEX IF NOT EXISTS idx_guidance_lookup
  ON guidance_cache(skill_name, client_id);

CREATE INDEX IF NOT EXISTS idx_patterns_level
  ON patterns(pattern_level, domain);

CREATE INDEX IF NOT EXISTS idx_patterns_skill_client
  ON patterns(skill_name, client_id);

CREATE INDEX IF NOT EXISTS idx_outcomes_tracking
  ON outcomes(tracking_id);
