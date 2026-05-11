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
    detected_at  TIMESTAMP DEFAULT current_timestamp
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
    recorded_at       TIMESTAMP DEFAULT current_timestamp
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
