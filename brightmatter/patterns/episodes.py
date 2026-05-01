"""Episode tracker — links change events to performance outcomes.

An episode is BrightMatter's core learning unit:
  change happened → measure performance before → measure performance after → record outcome

This is how BrightMatter learns which changes work and which don't,
and accumulates knowledge across 500 accounts over time.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from brightmatter.models.changes import Episode, EpisodeOutcome
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

PRE_WINDOW_DAYS = 7
POST_WINDOW_DAYS = 7
MIN_POST_DAYS = 5


class EpisodeTracker:
    """Creates episodes from change events and evaluates outcomes."""

    def __init__(self, repo: Repository, db: Database):
        self.repo = repo
        self.db = db

    def process_pending_episodes(self) -> list[Episode]:
        """Find change events that now have enough post-change data to evaluate."""
        cutoff = date.today() - timedelta(days=POST_WINDOW_DAYS + MIN_POST_DAYS)

        eligible_changes = self.db.fetchall("""
            SELECT ce.account_id, ce.change_id, ce.change_timestamp,
                   ce.change_type, ce.resource_type, ce.campaign_id,
                   ce.old_value, ce.new_value, ce.actor
            FROM change_events ce
            LEFT JOIN episodes ep ON ce.change_id = ep.change_event_id
            WHERE ep.episode_id IS NULL
              AND ce.change_timestamp::date <= ?
            ORDER BY ce.change_timestamp
            LIMIT 100
        """, [cutoff])

        episodes = []
        for row in eligible_changes:
            account_id, change_id, change_ts = row[0], row[1], row[2]
            change_date = change_ts.date() if isinstance(change_ts, datetime) else change_ts
            campaign_id = row[5] or ""

            pre = self._get_period_metrics(account_id, campaign_id,
                                           change_date - timedelta(days=PRE_WINDOW_DAYS), change_date)
            post = self._get_period_metrics(account_id, campaign_id,
                                            change_date, change_date + timedelta(days=POST_WINDOW_DAYS))

            if not pre or not post:
                continue

            outcome, magnitude, detail = self._evaluate_outcome(pre, post)

            episode = Episode(
                episode_id=uuid.uuid4().hex[:12],
                account_id=account_id,
                change_event_id=change_id,
                change_description=f"{row[3]} on {row[4]}",
                domain=self._infer_domain(row[3], row[4]),
                pre_metrics=pre,
                post_metrics=post,
                outcome=outcome,
                outcome_magnitude=magnitude,
                outcome_detail=detail,
                recorded_at=datetime.now(timezone.utc),
            )
            self.repo.insert_episode(episode)
            episodes.append(episode)

        return episodes

    def _get_period_metrics(self, account_id: str, campaign_id: str,
                            start: date, end: date) -> dict[str, Any]:
        campaign_filter = "AND campaign_id = ?" if campaign_id else ""
        params = [account_id, start, end]
        if campaign_id:
            params.insert(1, campaign_id)

        row = self.db.fetchone(f"""
            SELECT sum(impressions), sum(clicks), sum(cost_micros),
                   sum(conversions), sum(conversion_value), count(DISTINCT date)
            FROM daily_metrics
            WHERE account_id = ? {campaign_filter}
              AND date >= ? AND date < ?
        """, params)

        if not row or not row[5]:
            return {}

        clicks = row[1] or 0
        cost = (row[2] or 0) / 1_000_000
        conversions = row[3] or 0
        return {
            "impressions": row[0] or 0,
            "clicks": clicks,
            "cost": cost,
            "conversions": conversions,
            "conversion_value": row[4] or 0,
            "days": row[5],
            "ctr": clicks / row[0] if row[0] else 0,
            "cvr": conversions / clicks if clicks else 0,
            "cpa": cost / conversions if conversions else 0,
            "roas": (row[4] or 0) / cost if cost else 0,
        }

    def _evaluate_outcome(self, pre: dict, post: dict) -> tuple[EpisodeOutcome, float, str]:
        """Compare pre/post metrics to determine outcome.

        Primary metric: CPA for lead gen, ROAS for ecommerce.
        Falls back to CVR as the universal signal.
        """
        if not pre.get("conversions") or not post.get("conversions"):
            return EpisodeOutcome.NEUTRAL, 0.0, "Insufficient conversion data"

        pre_cvr = pre.get("cvr", 0)
        post_cvr = post.get("cvr", 0)
        pre_cpa = pre.get("cpa", 0)
        post_cpa = post.get("cpa", 0)

        if pre_cpa and post_cpa:
            cpa_change = (post_cpa - pre_cpa) / pre_cpa
            if cpa_change < -0.10:
                return EpisodeOutcome.IMPROVED, abs(cpa_change), f"CPA improved {abs(cpa_change):.0%}"
            if cpa_change > 0.10:
                return EpisodeOutcome.DEGRADED, abs(cpa_change), f"CPA degraded {abs(cpa_change):.0%}"

        if pre_cvr and post_cvr:
            cvr_change = (post_cvr - pre_cvr) / pre_cvr
            if cvr_change > 0.10:
                return EpisodeOutcome.IMPROVED, abs(cvr_change), f"CVR improved {abs(cvr_change):.0%}"
            if cvr_change < -0.10:
                return EpisodeOutcome.DEGRADED, abs(cvr_change), f"CVR degraded {abs(cvr_change):.0%}"

        return EpisodeOutcome.NEUTRAL, 0.0, "No significant change"

    def _infer_domain(self, change_type: str, resource_type: str) -> str:
        mapping = {
            "campaign_budget": "bidding_strategy",
            "campaign": "campaign_structure",
            "ad_group_criterion": "non_branded_search",
            "ad_group_ad": "creative",
            "bidding_strategy": "bidding_strategy",
        }
        return mapping.get(resource_type, "campaign_structure")
