"""Repository — typed CRUD operations over DuckDB for all BrightMatter models."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from brightmatter.models.account import Account
from brightmatter.models.changes import ChangeEvent, Episode
from brightmatter.models.metrics import DailyMetrics, KeywordMetrics
from brightmatter.models.patterns import Pattern, Signal
from brightmatter.storage.database import Database


class Repository:
    """All database read/write operations for BrightMatter data."""

    def __init__(self, db: Database):
        self.db = db

    # ── Accounts ──

    def upsert_account(self, account: Account) -> None:
        self.db.execute(
            """INSERT INTO accounts (account_id, account_name, mcc_id, business_type,
                   vertical, website_url, spend_tier, currency_code, first_seen, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (account_id) DO UPDATE SET
                   account_name = excluded.account_name,
                   business_type = excluded.business_type,
                   vertical = excluded.vertical,
                   website_url = excluded.website_url,
                   spend_tier = excluded.spend_tier,
                   last_updated = excluded.last_updated""",
            [
                account.account_id, account.account_name, account.mcc_id,
                account.business_type.value, account.vertical, account.website_url,
                account.spend_tier.value, account.currency_code,
                account.first_seen, account.last_updated or datetime.now(timezone.utc),
            ],
        )

    def get_account(self, account_id: str) -> Account | None:
        row = self.db.fetchone("SELECT * FROM accounts WHERE account_id = ?", [account_id])
        if not row:
            return None
        cols = ["account_id", "account_name", "mcc_id", "business_type", "vertical",
                "website_url", "spend_tier", "currency_code", "first_seen", "last_updated"]
        return Account(**dict(zip(cols, row)))

    def list_accounts(self) -> list[Account]:
        rows = self.db.fetchall("SELECT * FROM accounts ORDER BY account_name")
        cols = ["account_id", "account_name", "mcc_id", "business_type", "vertical",
                "website_url", "spend_tier", "currency_code", "first_seen", "last_updated"]
        return [Account(**dict(zip(cols, r))) for r in rows]

    # ── Daily Metrics ──

    def insert_daily_metrics(self, metrics: list[DailyMetrics]) -> int:
        if not metrics:
            return 0
        now = datetime.now(timezone.utc)
        values = []
        for m in metrics:
            values.append((
                m.account_id, m.campaign_id, m.campaign_name, m.campaign_type,
                m.date, m.impressions, m.clicks, m.cost_micros,
                m.conversions, m.conversion_value,
                m.search_impression_share, m.search_budget_lost_is,
                m.search_rank_lost_is, m.search_abs_top_is,
                m.bidding_strategy, m.bidding_target, m.daily_budget_micros,
                m.status, now,
            ))
        self.db.execute(
            """INSERT OR REPLACE INTO daily_metrics VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values[0],
        )
        for v in values[1:]:
            self.db.execute(
                """INSERT OR REPLACE INTO daily_metrics VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                v,
            )
        return len(values)

    def get_daily_metrics(
        self,
        account_id: str | None = None,
        campaign_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if account_id:
            clauses.append("account_id = ?")
            params.append(account_id)
        if campaign_id:
            clauses.append("campaign_id = ?")
            params.append(campaign_id)
        if start_date:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("date <= ?")
            params.append(end_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.fetchdf(f"SELECT * FROM daily_metrics {where} ORDER BY date", params)

    # ── Keyword Metrics ──

    def insert_keyword_metrics(self, metrics: list[KeywordMetrics]) -> int:
        if not metrics:
            return 0
        now = datetime.now(timezone.utc)
        for m in metrics:
            self.db.execute(
                """INSERT OR REPLACE INTO keyword_metrics VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m.account_id, m.campaign_id, m.ad_group_id, m.keyword_id,
                    m.keyword_text, m.match_type, m.week_start,
                    m.quality_score, m.expected_ctr, m.ad_relevance,
                    m.landing_page_experience, m.impressions, m.clicks,
                    m.cost_micros, m.conversions, now,
                ),
            )
        return len(metrics)

    # ── Change Events ──

    def insert_change_events(self, events: list[ChangeEvent]) -> int:
        if not events:
            return 0
        now = datetime.now(timezone.utc)
        for e in events:
            self.db.execute(
                """INSERT OR IGNORE INTO change_events VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.account_id, e.change_id, e.change_timestamp,
                    e.change_type, e.resource_type, e.resource_name,
                    e.campaign_id, e.campaign_name, e.actor.value,
                    e.actor_email, e.old_value, e.new_value, now,
                ),
            )
        return len(events)

    # ── Signals ──

    def insert_signal(self, signal: Signal) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.signal_id, signal.account_id, signal.campaign_id,
                signal.domain.value, signal.signal_type, signal.severity.value,
                signal.value, signal.threshold, signal.message,
                json.dumps(signal.data), signal.detected_at or datetime.now(timezone.utc),
            ),
        )

    def get_signals(self, account_id: str | None = None, domain: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if account_id:
            clauses.append("account_id = ?")
            params.append(account_id)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.fetchdf(f"SELECT * FROM signals {where} ORDER BY detected_at DESC", params)

    # ── Patterns ──

    def insert_pattern(self, pattern: Pattern) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO patterns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pattern.pattern_id, pattern.domain.value, pattern.pattern_type.value,
                pattern.severity.value, pattern.confidence,
                json.dumps(pattern.accounts_affected), pattern.summary,
                json.dumps(pattern.evidence), json.dumps(pattern.source_signals),
                pattern.detector, pattern.detected_at or datetime.now(timezone.utc),
            ),
        )

    def get_patterns(self, domain: str | None = None, min_confidence: float = 0.0) -> list[dict[str, Any]]:
        clauses, params = ["confidence >= ?"], [min_confidence]
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = f"WHERE {' AND '.join(clauses)}"
        return self.db.fetchdf(f"SELECT * FROM patterns {where} ORDER BY detected_at DESC", params)

    # ── Episodes ──

    def insert_episode(self, episode: Episode) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode.episode_id, episode.account_id, episode.change_event_id,
                episode.change_description, episode.domain,
                json.dumps(episode.pre_metrics), json.dumps(episode.post_metrics),
                episode.outcome.value, episode.outcome_magnitude,
                episode.outcome_detail, episode.recorded_at or datetime.now(timezone.utc),
            ),
        )

    def get_episodes(self, account_id: str | None = None, outcome: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if account_id:
            clauses.append("account_id = ?")
            params.append(account_id)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.fetchdf(f"SELECT * FROM episodes {where} ORDER BY recorded_at DESC", params)

    # ── Analytical queries ──

    def account_summary(self, account_id: str, days: int = 30) -> dict[str, Any]:
        """Aggregate performance for an account over N days."""
        row = self.db.fetchone(
            """SELECT
                   count(DISTINCT campaign_id) as campaigns,
                   sum(impressions) as impressions,
                   sum(clicks) as clicks,
                   sum(cost_micros) as cost_micros,
                   sum(conversions) as conversions,
                   sum(conversion_value) as conversion_value,
                   avg(search_impression_share) as avg_search_is
               FROM daily_metrics
               WHERE account_id = ? AND date >= current_date - ?""",
            [account_id, days],
        )
        if not row:
            return {}
        cols = ["campaigns", "impressions", "clicks", "cost_micros",
                "conversions", "conversion_value", "avg_search_is"]
        return dict(zip(cols, row))

    def cross_account_metrics(self, days: int = 30) -> list[dict[str, Any]]:
        """Per-account aggregate for cross-account comparison."""
        data = self.db.fetchdf(
            """SELECT
                   account_id,
                   count(DISTINCT campaign_id) as campaigns,
                   sum(impressions) as impressions,
                   sum(clicks) as clicks,
                   sum(cost_micros) as cost_micros,
                   sum(conversions) as conversions,
                   sum(conversion_value) as conversion_value
               FROM daily_metrics
               WHERE date >= current_date - ?
               GROUP BY account_id
               ORDER BY sum(cost_micros) DESC""",
            [days],
        )
        return data
