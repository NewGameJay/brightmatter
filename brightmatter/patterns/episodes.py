"""Episode tracker (Phase 1.5) — links batches of change events to performance.

An episode is a BATCH of same-category changes on one campaign on one day:
  changes happened -> performance before -> performance after -> outcome

PRELIMINARY by design: it records what happened and what performance looked
like before/after. It does NOT claim causation and applies NO trend
adjustment (that is Phase 2). Every episode carries the confidence frame —
what we know, what we can't rule out, what to check next — so the honest
limits travel with the record.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from brightmatter.models.changes import Episode, EpisodeOutcome
from brightmatter.patterns import change_taxonomy as tax
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

PRE_WINDOW_DAYS = 7
POST_WINDOW_DAYS = 7
MIN_DAYS = 4  # need at least this many days of data on each side


def _category_case_sql(column: str = "resource_type") -> str:
    """Build a SQL CASE that maps resource_type -> category from the taxonomy,
    so the grouping logic stays single-source with change_taxonomy."""
    whens = "\n".join(
        f"            WHEN upper({column}) = '{rt}' THEN '{cat}'"
        for rt, cat in tax._RESOURCE_TO_CATEGORY.items()
    )
    return f"CASE\n{whens}\n            ELSE 'other' END"


class EpisodeTracker:
    """Builds preliminary episodes from batched change events."""

    def __init__(self, repo: Repository, db: Database):
        self.repo = repo
        self.db = db

    def _anchor_range(self) -> tuple[date, date] | None:
        row = self.db.fetchone("SELECT min(date), max(date) FROM daily_metrics")
        if not row or row[0] is None:
            return None
        return row[0], row[1]

    def process_episodes(self, reset: bool = True) -> list[Episode]:
        rng = self._anchor_range()
        if rng is None:
            return []
        data_start, anchor = rng
        # A change is eligible only if a full pre- AND post-window of data exists.
        earliest = data_start + timedelta(days=PRE_WINDOW_DAYS)
        latest = anchor - timedelta(days=POST_WINDOW_DAYS)
        if earliest >= latest:
            return []

        if reset:
            self.db.execute("DELETE FROM episodes")

        case_sql = _category_case_sql()
        batches = self.db.fetchall(f"""
            SELECT account_id,
                   COALESCE(campaign_id, '') as cid,
                   CAST(change_timestamp AS DATE) as cdate,
                   {case_sql} as category,
                   count(*) as cnt,
                   count(*) FILTER (WHERE actor = 'auto_applied') as auto_cnt,
                   count(*) FILTER (WHERE actor = 'human') as human_cnt,
                   min(change_id) as rep_id,
                   max(resource_type) as sample_resource
            FROM change_events
            WHERE CAST(change_timestamp AS DATE) >= ?
              AND CAST(change_timestamp AS DATE) <= ?
            GROUP BY account_id, cid, cdate, category
        """, [earliest, latest])

        # Index batches per (account, campaign) for confounding detection.
        by_campaign: dict[tuple[str, str], list[dict]] = defaultdict(list)
        rows = []
        for (acct, cid, cdate, category, cnt, auto_cnt, human_cnt, rep_id, sample_rt) in batches:
            cdate = cdate if isinstance(cdate, date) else date.fromisoformat(str(cdate))
            b = {"acct": acct, "cid": cid, "cdate": cdate, "category": category,
                 "cnt": cnt, "auto": auto_cnt or 0, "human": human_cnt or 0,
                 "rep_id": rep_id, "sample_rt": sample_rt}
            rows.append(b)
            by_campaign[(acct, cid)].append(b)

        episodes: list[Episode] = []
        for b in rows:
            pre = self._period_metrics(b["acct"], b["cid"],
                                       b["cdate"] - timedelta(days=PRE_WINDOW_DAYS), b["cdate"])
            post = self._period_metrics(b["acct"], b["cid"],
                                        b["cdate"], b["cdate"] + timedelta(days=POST_WINDOW_DAYS))
            if not pre or not post:
                continue
            if pre["days"] < MIN_DAYS or post["days"] < MIN_DAYS:
                continue

            confounders = self._confounders(by_campaign[(b["acct"], b["cid"])], b)
            outcome, magnitude, detail = self._evaluate_outcome(pre, post)
            if confounders:
                outcome = EpisodeOutcome.CONFOUNDED

            actor = ("auto_applied" if b["human"] == 0 else
                     "human" if b["auto"] == 0 else "mixed")
            cat_label = tax.label(b["category"])
            scope = "campaign" if b["cid"] else "account"
            frame = self._confidence(b, cat_label, scope, pre, post, outcome, detail, confounders)

            ep = Episode(
                episode_id=uuid.uuid4().hex[:12],
                account_id=b["acct"],
                change_event_id=b["rep_id"] or "",
                campaign_id=b["cid"],
                change_description=f"{b['cnt']}x {cat_label} ({actor}) on {b['cdate']}",
                domain=self._infer_domain(b["category"]),
                change_category=b["category"],
                change_count=b["cnt"],
                actor=actor,
                confounded=bool(confounders),
                pre_metrics=pre,
                post_metrics=post,
                outcome=outcome,
                outcome_magnitude=magnitude,
                outcome_detail=detail,
                confidence_tier=frame[0],
                what_we_know=frame[1],
                what_we_cant_rule_out=frame[2],
                check_next=frame[3],
                recorded_at=datetime.now(timezone.utc),
            )
            self.repo.insert_episode(ep)
            episodes.append(ep)

        return episodes

    # Backwards-compatible alias (engine.py calls process_pending_episodes).
    def process_pending_episodes(self) -> list[Episode]:
        return self.process_episodes(reset=True)

    def _confounders(self, campaign_batches: list[dict], b: dict) -> list[str]:
        """Other change categories on the same campaign within this batch's
        post-window — they make single-cause attribution impossible."""
        out = []
        for other in campaign_batches:
            if other is b or other["category"] == b["category"]:
                continue
            if b["cdate"] <= other["cdate"] < b["cdate"] + timedelta(days=POST_WINDOW_DAYS):
                out.append(other["category"])
        return sorted(set(out))

    def _period_metrics(self, account_id: str, campaign_id: str,
                        start: date, end: date) -> dict[str, Any]:
        campaign_filter = "AND campaign_id = ?" if campaign_id else ""
        params: list[Any] = [account_id]
        if campaign_id:
            params.append(campaign_id)
        params += [start, end]
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
        conv = row[3] or 0
        return {
            "impressions": row[0] or 0, "clicks": clicks, "cost": round(cost, 2),
            "conversions": conv, "conversion_value": round(row[4] or 0, 2),
            "days": row[5],
            "cvr": round(conv / clicks, 4) if clicks else 0,
            "cpa": round(cost / conv, 2) if conv else 0,
            "roas": round((row[4] or 0) / cost, 2) if cost else 0,
        }

    def _evaluate_outcome(self, pre: dict, post: dict) -> tuple[EpisodeOutcome, float, str]:
        if not pre.get("conversions") or not post.get("conversions"):
            return EpisodeOutcome.NEUTRAL, 0.0, "Insufficient conversion data to read an outcome"
        pre_cpa, post_cpa = pre.get("cpa", 0), post.get("cpa", 0)
        if pre_cpa and post_cpa:
            d = (post_cpa - pre_cpa) / pre_cpa
            if d < -0.10:
                return EpisodeOutcome.IMPROVED, abs(d), f"CPA ${pre_cpa:.0f}→${post_cpa:.0f} ({d:+.0%})"
            if d > 0.10:
                return EpisodeOutcome.DEGRADED, abs(d), f"CPA ${pre_cpa:.0f}→${post_cpa:.0f} ({d:+.0%})"
        pre_cvr, post_cvr = pre.get("cvr", 0), post.get("cvr", 0)
        if pre_cvr and post_cvr:
            d = (post_cvr - pre_cvr) / pre_cvr
            if d > 0.10:
                return EpisodeOutcome.IMPROVED, abs(d), f"CVR {pre_cvr:.1%}→{post_cvr:.1%} ({d:+.0%})"
            if d < -0.10:
                return EpisodeOutcome.DEGRADED, abs(d), f"CVR {pre_cvr:.1%}→{post_cvr:.1%} ({d:+.0%})"
        return EpisodeOutcome.NEUTRAL, 0.0, "No material CPA/CVR movement"

    def _confidence(self, b: dict, cat_label: str, scope: str, pre: dict, post: dict,
                    outcome: EpisodeOutcome, detail: str,
                    confounders: list[str]) -> tuple[str, str, str, str]:
        where = f"campaign {b['cid']}" if b["cid"] else "the account"
        know = (f"{b['cnt']} {cat_label}(s) ({b['cnt'] and ('auto-applied' if b['human']==0 else 'human' if b['auto']==0 else 'mixed')}) "
                f"on {where} on {b['cdate']}. {detail}. "
                f"Pre {PRE_WINDOW_DAYS}d: CPA ${pre['cpa']:.0f}, CVR {pre['cvr']:.1%}, {pre['conversions']:.0f} conv; "
                f"post {POST_WINDOW_DAYS}d: CPA ${post['cpa']:.0f}, CVR {post['cvr']:.1%}, {post['conversions']:.0f} conv.")
        cant_bits = [
            "the metric may already have been trending before the change (no trend adjustment applied — that's Phase 2)",
            "seasonal demand or competitor shifts in the same window",
        ]
        if confounders:
            cant_bits.insert(0, f"other changes hit the same {scope} in the window ({', '.join(confounders)}) — "
                                f"the outcome cannot be attributed to this change alone")
        cant = "Can't rule out: " + "; ".join(cant_bits) + "."
        check = (f"Was CPA/CVR already moving before {b['cdate']}? "
                 + ("Untangle the overlapping changes listed above. " if confounders else "")
                 + "Trend-adjusted attribution comes in Phase 2.")
        # Confounded or any movement -> SUGGESTIVE (we see it, can't attribute the cause).
        # A genuinely flat outcome is a CONFIRMED factual "nothing moved".
        tier = "CONFIRMED" if outcome == EpisodeOutcome.NEUTRAL else "SUGGESTIVE"
        return tier, know, cant, check

    def _infer_domain(self, category: str) -> str:
        mapping = {
            "budget": "bidding_strategy", "bidding": "bidding_strategy",
            "campaign_setting": "campaign_structure", "structure": "campaign_structure",
            "targeting_keyword": "non_branded_search", "ad_creative": "creative",
            "asset": "creative", "conversion": "landing_page",
        }
        return mapping.get(category, "campaign_structure")
