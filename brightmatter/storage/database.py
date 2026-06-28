"""DuckDB database — schema creation and connection management."""

from __future__ import annotations

from pathlib import Path

import duckdb

from brightmatter.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id     TEXT PRIMARY KEY,
    account_name   TEXT,
    mcc_id         TEXT,
    business_type  TEXT DEFAULT 'unknown',
    vertical       TEXT DEFAULT '',
    website_url    TEXT DEFAULT '',
    spend_tier     TEXT DEFAULT '<5k',
    currency_code  TEXT DEFAULT 'USD',
    first_seen     DATE,
    last_updated   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    account_id             TEXT NOT NULL,
    campaign_id            TEXT NOT NULL,
    campaign_name          TEXT,
    campaign_type          TEXT,
    date                   DATE NOT NULL,
    impressions            BIGINT DEFAULT 0,
    clicks                 BIGINT DEFAULT 0,
    cost_micros            BIGINT DEFAULT 0,
    conversions            DOUBLE DEFAULT 0,
    conversion_value       DOUBLE DEFAULT 0,
    search_impression_share DOUBLE,
    search_budget_lost_is  DOUBLE,
    search_rank_lost_is    DOUBLE,
    search_abs_top_is      DOUBLE,
    bidding_strategy       TEXT,
    bidding_target         DOUBLE,
    daily_budget_micros    BIGINT DEFAULT 0,
    status                 TEXT DEFAULT 'ENABLED',
    ingested_at            TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, date)
);

CREATE TABLE IF NOT EXISTS campaign_configs (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    snapshot_date  DATE NOT NULL,
    campaign_name  TEXT,
    campaign_type  TEXT,
    status         TEXT,
    bidding_strategy TEXT,
    bidding_target DOUBLE,
    daily_budget_micros BIGINT,
    network_search BOOLEAN,
    network_search_partners BOOLEAN,
    network_display BOOLEAN,
    geo_targets    TEXT,
    language_codes TEXT,
    start_date     DATE,
    end_date       DATE,
    PRIMARY KEY (account_id, campaign_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS keyword_metrics (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    ad_group_id    TEXT NOT NULL,
    keyword_id     TEXT NOT NULL,
    keyword_text   TEXT,
    match_type     TEXT,
    week_start     DATE NOT NULL,
    quality_score  INTEGER,
    expected_ctr   TEXT,
    ad_relevance   TEXT,
    landing_page_experience TEXT,
    impressions    BIGINT DEFAULT 0,
    clicks         BIGINT DEFAULT 0,
    cost_micros    BIGINT DEFAULT 0,
    conversions    DOUBLE DEFAULT 0,
    ingested_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, keyword_id, week_start)
);

CREATE TABLE IF NOT EXISTS change_events (
    account_id       TEXT NOT NULL,
    change_id        TEXT NOT NULL,
    change_timestamp TIMESTAMP NOT NULL,
    change_type      TEXT,
    resource_type    TEXT,
    resource_name    TEXT,
    campaign_id      TEXT,
    campaign_name    TEXT,
    actor            TEXT DEFAULT 'unknown',
    actor_email      TEXT DEFAULT '',
    old_value        TEXT,
    new_value        TEXT,
    ingested_at      TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, change_id)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id    TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    campaign_id  TEXT DEFAULT '',
    domain       TEXT NOT NULL,
    signal_type  TEXT,
    severity     TEXT DEFAULT 'info',
    value        DOUBLE,
    threshold    DOUBLE,
    message      TEXT,
    data_json    TEXT,
    detected_at  TIMESTAMP DEFAULT current_timestamp,
    confidence_tier        TEXT DEFAULT '',
    what_we_know           TEXT DEFAULT '',
    what_we_cant_rule_out  TEXT DEFAULT '',
    check_next             TEXT DEFAULT '',
    trend_context          TEXT DEFAULT '',
    trend_slope_30d        DOUBLE,
    trend_classification_30d TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS patterns (
    pattern_id        TEXT PRIMARY KEY,
    domain            TEXT NOT NULL,
    pattern_type      TEXT DEFAULT 'threshold_violation',
    severity          TEXT DEFAULT 'info',
    confidence        DOUBLE DEFAULT 0,
    accounts_affected TEXT,
    summary           TEXT,
    evidence_json     TEXT,
    source_signals    TEXT,
    detector          TEXT,
    detected_at       TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS asset_coverage (
    account_id      TEXT NOT NULL,
    campaign_id     TEXT NOT NULL,
    asset_type      TEXT NOT NULL,
    asset_count     INTEGER DEFAULT 0,
    ingested_at     TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, asset_type)
);

CREATE TABLE IF NOT EXISTS keyword_counts (
    account_id      TEXT NOT NULL,
    campaign_id     TEXT NOT NULL,
    campaign_name   TEXT,
    keyword_count   INTEGER DEFAULT 0,
    broad_count     INTEGER DEFAULT 0,
    phrase_count    INTEGER DEFAULT 0,
    exact_count     INTEGER DEFAULT 0,
    negative_count  INTEGER DEFAULT 0,
    ingested_at     TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id)
);

CREATE TABLE IF NOT EXISTS conversion_actions (
    account_id         TEXT NOT NULL,
    action_id          TEXT NOT NULL,
    action_name        TEXT,
    status             TEXT,
    action_type        TEXT,
    category           TEXT,
    primary_for_goal   BOOLEAN,
    counting_type      TEXT,
    attribution_model  TEXT,
    ingested_at        TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, action_id)
);

CREATE TABLE IF NOT EXISTS search_terms (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    campaign_name  TEXT,
    search_term    TEXT NOT NULL,
    window_start   DATE NOT NULL,
    window_end     DATE NOT NULL,
    impressions    BIGINT DEFAULT 0,
    clicks         BIGINT DEFAULT 0,
    cost_micros    BIGINT DEFAULT 0,
    conversions    DOUBLE DEFAULT 0,
    conversions_value DOUBLE DEFAULT 0,
    ingested_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, search_term, window_start)
);

CREATE TABLE IF NOT EXISTS account_web_meta (
    account_id   TEXT PRIMARY KEY,
    title        TEXT,
    description  TEXT,
    status_code  INTEGER,
    fetched_at   TIMESTAMP DEFAULT current_timestamp,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id        TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL,
    change_event_id   TEXT NOT NULL,
    change_description TEXT,
    domain            TEXT,
    pre_metrics_json  TEXT,
    post_metrics_json TEXT,
    outcome           TEXT DEFAULT 'pending',
    outcome_magnitude DOUBLE DEFAULT 0,
    outcome_detail    TEXT,
    recorded_at       TIMESTAMP DEFAULT current_timestamp,
    campaign_id       TEXT DEFAULT '',
    change_category   TEXT DEFAULT '',
    change_count      INTEGER DEFAULT 1,
    actor             TEXT DEFAULT '',
    confounded        BOOLEAN DEFAULT FALSE,
    confidence_tier        TEXT DEFAULT '',
    what_we_know           TEXT DEFAULT '',
    what_we_cant_rule_out  TEXT DEFAULT '',
    check_next             TEXT DEFAULT '',
    trend_adjusted         BOOLEAN DEFAULT FALSE,
    trend_slope            DOUBLE DEFAULT 0,
    expected_value         DOUBLE DEFAULT 0,
    raw_magnitude          DOUBLE DEFAULT 0,
    adjusted_magnitude     DOUBLE DEFAULT 0,
    trend_contribution_pct DOUBLE DEFAULT 0
);

CREATE TABLE IF NOT EXISTS campaign_trends (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    metric         TEXT NOT NULL,
    window_days    INTEGER NOT NULL,
    slope          DOUBLE,
    p_value        DOUBLE,
    r_squared      DOUBLE,
    classification TEXT,
    cv             DOUBLE,
    current_value  DOUBLE,
    projected_7d   DOUBLE,
    volatility_cv       DOUBLE,
    volatility_class    TEXT DEFAULT '',
    threshold_multiplier DOUBLE DEFAULT 1.0,
    computed_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, metric, window_days)
);

CREATE TABLE IF NOT EXISTS regime_changes (
    account_id   TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    metric       TEXT NOT NULL,
    change_date  DATE NOT NULL,
    pre_mean     DOUBLE,
    post_mean    DOUBLE,
    shift_magnitude DOUBLE,
    shift_direction TEXT,
    segment_days_before INTEGER,
    segment_days_after  INTEGER,
    computed_at  TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, metric, change_date)
);

-- ── Phase 3: segment-scoped learning ──
CREATE TABLE IF NOT EXISTS segments (
    segment_id   TEXT PRIMARY KEY,
    dimension    TEXT NOT NULL,
    value        TEXT NOT NULL,
    n_accounts   INTEGER DEFAULT 0,
    n_episodes   INTEGER DEFAULT 0,
    computed_at  TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS segment_patterns (
    segment_id        TEXT NOT NULL,
    dimension         TEXT NOT NULL,
    value             TEXT NOT NULL,
    change_category   TEXT NOT NULL,
    actor             TEXT NOT NULL,
    n                 INTEGER DEFAULT 0,
    n_accounts        INTEGER DEFAULT 0,
    degraded          INTEGER DEFAULT 0,
    improved          INTEGER DEFAULT 0,
    neutral           INTEGER DEFAULT 0,
    degraded_rate     DOUBLE DEFAULT 0,
    degraded_ci_low   DOUBLE DEFAULT 0,
    degraded_ci_high  DOUBLE DEFAULT 0,
    improved_rate     DOUBLE DEFAULT 0,
    improved_ci_low   DOUBLE DEFAULT 0,
    improved_ci_high  DOUBLE DEFAULT 0,
    confidence        TEXT DEFAULT '',
    computed_at       TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (segment_id, change_category, actor)
);

CREATE TABLE IF NOT EXISTS segment_comparisons (
    segment_id             TEXT NOT NULL,
    dimension              TEXT NOT NULL,
    value                  TEXT NOT NULL,
    change_category        TEXT NOT NULL,
    actor                  TEXT NOT NULL,
    n_segment              INTEGER DEFAULT 0,
    n_rest                 INTEGER DEFAULT 0,
    degraded_rate_segment  DOUBLE DEFAULT 0,
    degraded_rate_rest     DOUBLE DEFAULT 0,
    rate_delta             DOUBLE DEFAULT 0,
    z                      DOUBLE DEFAULT 0,
    p_value                DOUBLE DEFAULT 1,
    significant            BOOLEAN DEFAULT FALSE,
    direction              TEXT DEFAULT '',
    computed_at            TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (segment_id, change_category, actor)
);

-- ── Phase 4: state-conditioned templates ──
CREATE TABLE IF NOT EXISTS templates (
    template_id          TEXT NOT NULL,
    version              INTEGER NOT NULL,
    conditions_json      TEXT,
    level                INTEGER DEFAULT 0,
    prediction_direction TEXT,
    prediction_magnitude DOUBLE,
    magnitude_iqr_low    DOUBLE,
    magnitude_iqr_high   DOUBLE,
    n_episodes           INTEGER DEFAULT 0,
    n_accounts           INTEGER DEFAULT 0,
    n_folds              INTEGER DEFAULT 0,
    direction_accuracy   DOUBLE DEFAULT 0,
    magnitude_mae        DOUBLE DEFAULT 0,
    status               TEXT DEFAULT '',
    created_at           TEXT,
    last_validated       TEXT,
    retired_at           TEXT,
    changelog            TEXT,
    natural_magnitude              DOUBLE,
    action_attributable_magnitude  DOUBLE,
    PRIMARY KEY (template_id, version)
);

CREATE TABLE IF NOT EXISTS template_predictions (
    template_id          TEXT NOT NULL,
    template_version     INTEGER DEFAULT 0,
    episode_id           TEXT,
    predicted_direction  TEXT,
    predicted_magnitude  DOUBLE,
    actual_direction     TEXT,
    actual_magnitude     DOUBLE,
    direction_correct    BOOLEAN,
    magnitude_error      DOUBLE,
    magnitude_score      TEXT,
    predicted_at         TIMESTAMP DEFAULT current_timestamp,
    resolved_at          TIMESTAMP,
    source               TEXT DEFAULT 'backtest'
);

-- ── Phase 4.5 — refinement layers ──
CREATE TABLE IF NOT EXISTS baseline_observations (
    account_id      TEXT NOT NULL,
    campaign_id     TEXT NOT NULL,
    state           TEXT,
    window_start    DATE,
    window_end      DATE,
    cpa_start       DOUBLE,
    cpa_end         DOUBLE,
    cpa_change_pct  DOUBLE,
    had_action      BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS template_exceptions (
    template_id          TEXT NOT NULL,
    exception_dim        TEXT,
    exception_value      TEXT,
    n_exception          INTEGER,
    n_accounts           INTEGER,
    base_prediction      TEXT,
    exception_direction  TEXT,
    exception_magnitude  DOUBLE,
    p_value              DOUBLE,
    flips                BOOLEAN,
    computed_at          TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS magnitude_convergence (
    template_id         TEXT NOT NULL,
    observation_number  INTEGER,
    predicted_magnitude DOUBLE,
    actual_magnitude    DOUBLE,
    running_estimate    DOUBLE,
    running_mae         DOUBLE,
    computed_at         TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS matched_controls (
    episode_id            TEXT NOT NULL,
    campaign_id           TEXT,
    state                 TEXT,
    action_cpa_change     DOUBLE,
    no_action_cpa_change  DOUBLE,
    matched_attribution   DOUBLE,
    match_quality         TEXT,
    baseline_window_start DATE,
    computed_at           TIMESTAMP DEFAULT current_timestamp
);

-- ── Phase 4.75 — segment dimensions (window-aggregated per campaign) ──
CREATE TABLE IF NOT EXISTS campaign_segments (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    dimension      TEXT NOT NULL,   -- device | network | hour | dow | geo
    segment_value  TEXT NOT NULL,
    impressions    BIGINT DEFAULT 0,
    clicks         BIGINT DEFAULT 0,
    cost_micros    BIGINT DEFAULT 0,
    conversions    DOUBLE DEFAULT 0,
    window_start   DATE,
    window_end     DATE,
    ingested_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, dimension, segment_value)
);

CREATE TABLE IF NOT EXISTS ad_strength (
    account_id    TEXT NOT NULL,
    campaign_id   TEXT NOT NULL,
    ad_group_id   TEXT NOT NULL,
    ad_id         TEXT NOT NULL,
    ad_strength   TEXT,
    ingested_at   TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, ad_group_id, ad_id)
);

-- ── Phase 5 — continuous operation ──
CREATE TABLE IF NOT EXISTS live_predictions (
    prediction_id          TEXT PRIMARY KEY,
    template_id            TEXT NOT NULL,
    episode_id             TEXT,
    account_id             TEXT,
    campaign_id            TEXT,
    state                  TEXT,
    predicted_direction    TEXT,
    predicted_magnitude    DOUBLE,
    natural_magnitude      DOUBLE,
    action_cost_predicted  DOUBLE,
    recommendation         TEXT,
    registered_at          DATE,
    source                 TEXT DEFAULT 'live'
);

CREATE TABLE IF NOT EXISTS prediction_resolutions (
    prediction_id           TEXT NOT NULL,
    window_days             INTEGER NOT NULL,
    actual_magnitude        DOUBLE,
    actual_direction        TEXT,
    direction_correct       BOOLEAN,
    magnitude_error         DOUBLE,
    magnitude_score         TEXT,
    actual_action_cost      DOUBLE,
    recommendation_correct  BOOLEAN,
    resolved_at             TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (prediction_id, window_days)
);

CREATE TABLE IF NOT EXISTS template_health (
    template_id                   TEXT PRIMARY KEY,
    n_resolved                    INTEGER,
    live_direction_accuracy       DOUBLE,
    live_recommendation_accuracy  DOUBLE,
    magnitude_mae                 DOUBLE,
    backtest_direction_accuracy   DOUBLE,
    status                        TEXT,
    drift_flag                    TEXT,
    updated_at                    TIMESTAMP DEFAULT current_timestamp
);

-- ── GA4 Phase 1 — property -> Ads account mapping (metadata only) ──
CREATE TABLE IF NOT EXISTS ga4_property_map (
    account_id     TEXT NOT NULL,
    account_name   TEXT,
    account_url    TEXT,
    ga4_property   TEXT,
    ga4_name       TEXT,
    ga4_url        TEXT,
    match_method   TEXT,          -- url_domain | name_token | unmatched
    match_confidence TEXT,        -- high | low | none
    computed_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id)
);

-- ── GA4 x Google Ads cross-platform links (confidence upgrades) ──
CREATE TABLE IF NOT EXISTS cross_platform_links (
    signal_id      TEXT NOT NULL,
    account_id     TEXT,
    campaign_id    TEXT,
    signal_type    TEXT,
    matched_page   TEXT,
    chain          TEXT,        -- chain_1_landing_page | chain_2_mobile_ux
    ga4_evidence   TEXT,
    old_tier       TEXT,
    new_tier       TEXT,
    computed_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (signal_id, matched_page)
);

-- ── Google Ads campaign final URLs (for the GA4<->Ads page join) ──
CREATE TABLE IF NOT EXISTS campaign_final_urls (
    account_id    TEXT NOT NULL,
    campaign_id   TEXT NOT NULL,
    channel       TEXT,
    final_url     TEXT NOT NULL,
    norm_path     TEXT,     -- path only, lowercased, no query/trailing-slash (joins to GA4 landing_page)
    domain        TEXT,
    source        TEXT,     -- ad_group_ad | asset_group
    ingested_at   TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, final_url)
);

-- ── GA4 ingestion (research/ga4 signal map) ──
CREATE TABLE IF NOT EXISTS ga4_landing_pages (
    ga4_property      TEXT NOT NULL,
    account_id        TEXT,
    date              DATE NOT NULL,
    landing_page      TEXT NOT NULL,   -- normalized path
    device            TEXT NOT NULL,   -- mobile / desktop / tablet
    sessions          INTEGER DEFAULT 0,
    engaged_sessions  INTEGER DEFAULT 0,
    engagement_rate   DOUBLE DEFAULT 0,
    bounce_rate       DOUBLE DEFAULT 0,
    avg_session_duration DOUBLE DEFAULT 0,
    session_cvr       DOUBLE DEFAULT 0,
    key_events        DOUBLE DEFAULT 0,
    revenue           DOUBLE DEFAULT 0,
    ingested_at       TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (ga4_property, date, landing_page, device)
);

CREATE TABLE IF NOT EXISTS ga4_property_health (
    ga4_property      TEXT PRIMARY KEY,
    account_id        TEXT,
    overall_engagement_rate DOUBLE,
    key_events_per_session  DOUBLE,
    implementation_ok BOOLEAN,         -- false = engagement looks misconfigured (key_event on every view)
    note              TEXT,
    checked_at        TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS page_speed (
    url            TEXT NOT NULL,
    account_id     TEXT,
    form_factor    TEXT NOT NULL,      -- PHONE / DESKTOP
    lcp_ms         DOUBLE,
    cls            DOUBLE,
    inp_ms         DOUBLE,
    lcp_category   TEXT,
    cls_category   TEXT,
    inp_category   TEXT,
    fetched_at     TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (url, form_factor)
);

CREATE TABLE IF NOT EXISTS ga4_funnel_events (
    ga4_property   TEXT NOT NULL,
    account_id     TEXT,
    date           DATE NOT NULL,
    event_name     TEXT NOT NULL,      -- view_item / add_to_cart / begin_checkout / purchase
    event_count    INTEGER DEFAULT 0,
    ingested_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (ga4_property, date, event_name)
);

-- ── Phase 6.75 — per-metric predictions ──
CREATE TABLE IF NOT EXISTS per_metric_predictions (
    template_id   TEXT NOT NULL,
    metric        TEXT NOT NULL,
    median_delta  DOUBLE,
    iqr_low       DOUBLE,
    iqr_high      DOUBLE,
    mae           DOUBLE,
    n             INTEGER,
    computed_at   TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (template_id, metric)
);

CREATE TABLE IF NOT EXISTS metric_predictions (
    prediction_id        TEXT PRIMARY KEY,
    episode_id           TEXT,
    template_id          TEXT,
    metric               TEXT,
    predicted_median     DOUBLE,
    predicted_iqr_low    DOUBLE,
    predicted_iqr_high   DOUBLE,
    actual_delta         DOUBLE,
    error                DOUBLE,
    within_iqr           BOOLEAN,
    resolved             BOOLEAN DEFAULT FALSE,
    registered_at        DATE,
    resolved_at          TIMESTAMP DEFAULT current_timestamp
);
"""


class Database:
    """Manages the DuckDB connection and schema lifecycle."""

    def __init__(self, path: Path | str | None = None):
        self._path = str(path or DB_PATH)
        self._conn: duckdb.DuckDBPyConnection | None = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._path)
        return self._conn

    def initialize(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.execute(SCHEMA_SQL)
        # Migrate pre-existing DBs to the confidence-framework columns.
        for col in ("confidence_tier", "what_we_know",
                    "what_we_cant_rule_out", "check_next",
                    "trend_context", "trend_classification_30d"):
            try:
                self.conn.execute(
                    f"ALTER TABLE signals ADD COLUMN IF NOT EXISTS {col} TEXT DEFAULT ''"
                )
            except Exception:
                pass
        try:
            self.conn.execute(
                "ALTER TABLE signals ADD COLUMN IF NOT EXISTS trend_slope_30d DOUBLE"
            )
        except Exception:
            pass
        # Migrate episodes to the Phase 1.5 batch/taxonomy/confidence columns.
        _episode_cols = [
            ("campaign_id", "TEXT DEFAULT ''"), ("change_category", "TEXT DEFAULT ''"),
            ("change_count", "INTEGER DEFAULT 1"), ("actor", "TEXT DEFAULT ''"),
            ("confounded", "BOOLEAN DEFAULT FALSE"),
            ("confidence_tier", "TEXT DEFAULT ''"), ("what_we_know", "TEXT DEFAULT ''"),
            ("what_we_cant_rule_out", "TEXT DEFAULT ''"), ("check_next", "TEXT DEFAULT ''"),
            ("trend_adjusted", "BOOLEAN DEFAULT FALSE"), ("trend_slope", "DOUBLE DEFAULT 0"),
            ("expected_value", "DOUBLE DEFAULT 0"), ("raw_magnitude", "DOUBLE DEFAULT 0"),
            ("adjusted_magnitude", "DOUBLE DEFAULT 0"), ("trend_contribution_pct", "DOUBLE DEFAULT 0"),
            # Phase 4: pre-change performance state
            ("pre_state", "TEXT DEFAULT ''"), ("own_cpa_ratio", "DOUBLE DEFAULT 0"),
            ("bench_cpa_ratio", "DOUBLE DEFAULT 0"),
        ]
        for col, decl in _episode_cols:
            try:
                self.conn.execute(
                    f"ALTER TABLE episodes ADD COLUMN IF NOT EXISTS {col} {decl}"
                )
            except Exception:
                pass
        # Phase 4.5: mean-reversion columns on the template catalog.
        for col in ("natural_magnitude", "action_attributable_magnitude"):
            try:
                self.conn.execute(
                    f"ALTER TABLE templates ADD COLUMN IF NOT EXISTS {col} DOUBLE"
                )
            except Exception:
                pass

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: list | tuple | None = None) -> duckdb.DuckDBPyConnection:
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def fetchall(self, sql: str, params: list | tuple | None = None) -> list[tuple]:
        return self.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: list | tuple | None = None) -> tuple | None:
        return self.execute(sql, params).fetchone()

    def fetchdf(self, sql: str, params: list | tuple | None = None):
        """Return results as a dict of lists (lightweight, no pandas dependency)."""
        cursor = self.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return {col: [row[i] for row in rows] for i, col in enumerate(columns)}
