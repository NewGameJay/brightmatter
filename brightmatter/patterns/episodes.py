"""Episode tracker (Phase 1.5 + 1.75) — links change BUNDLES to performance.

An episode is one campaign-day-actor BUNDLE: all the change categories one
actor applied to one campaign on one day, classified via bundle_signatures.
Google auto-applies eligible recommendations together, so a recurring
multi-category set (budget + campaign_setting) is ONE coordinated action — not
several confounding changes. Recognizing known bundles recovers episodes the
naive per-category view marks confounded.

PRELIMINARY by design: records what changed and performance before/after; never
claims causation; no trend adjustment (Phase 2). Every episode carries the
confidence frame. Confounding is tracked cross-day and cross-actor: a clean
bundle has no other action on the same campaign in its post-window.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from brightmatter.models.changes import Episode, EpisodeOutcome
from brightmatter.patterns import bundle_signatures as bsig
from brightmatter.patterns import change_taxonomy as tax
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

PRE_WINDOW_DAYS = 7
POST_WINDOW_DAYS = 7
MIN_DAYS = 4


def _category_case_sql(column: str = "resource_type") -> str:
    whens = "\n".join(
        f"                WHEN upper({column}) = '{rt}' THEN '{cat}'"
        for rt, cat in tax._RESOURCE_TO_CATEGORY.items()
    )
    return f"CASE\n{whens}\n                ELSE 'other' END"


class EpisodeTracker:
    """Builds preliminary bundle episodes from batched change events."""

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
        earliest = data_start + timedelta(days=PRE_WINDOW_DAYS)
        latest = anchor - timedelta(days=POST_WINDOW_DAYS)
        if earliest >= latest:
            return []

        if reset:
            self.db.execute("DELETE FROM episodes")

        case_sql = _category_case_sql()
        # One row per (account, campaign, day, actor) bundle, with its category set.
        raw = self.db.fetchall(f"""
            WITH ev AS (
                SELECT account_id,
                       COALESCE(campaign_id, '') as cid,
                       CAST(change_timestamp AS DATE) as cdate,
                       actor,
                       {case_sql} as category,
                       change_id
                FROM change_events
                WHERE CAST(change_timestamp AS DATE) >= ?
                  AND CAST(change_timestamp AS DATE) <= ?
            )
            SELECT account_id, cid, cdate, actor,
                   list(DISTINCT category) as categories,
                   count(*) as cnt,
                   min(change_id) as rep_id
            FROM ev
            GROUP BY account_id, cid, cdate, actor
        """, [earliest, latest])

        # All bundles per campaign, for cross-day/cross-actor confound detection.
        by_campaign: dict[tuple[str, str], list[dict]] = defaultdict(list)
        bundles = []
        for acct, cid, cdate, actor, categories, cnt, rep_id in raw:
            cdate = cdate if isinstance(cdate, date) else date.fromisoformat(str(cdate))
            cats = frozenset(categories)
            label, known = bsig.classify_bundle(cats, actor)
            b = {"acct": acct, "cid": cid, "cdate": cdate, "actor": actor,
                 "cats": cats, "label": label, "known": known,
                 "cnt": cnt, "rep_id": rep_id}
            bundles.append(b)
            by_campaign[(acct, cid)].append(b)

        episodes: list[Episode] = []
        for b in bundles:
            pre = self._period_metrics(b["acct"], b["cid"],
                                       b["cdate"] - timedelta(days=PRE_WINDOW_DAYS), b["cdate"])
            post = self._period_metrics(b["acct"], b["cid"],
                                        b["cdate"], b["cdate"] + timedelta(days=POST_WINDOW_DAYS))
            if not pre or not post or pre["days"] < MIN_DAYS or post["days"] < MIN_DAYS:
                continue

            # Confounders: any OTHER campaign action (different day or different
            # actor) within this bundle's post-window. An unknown multi-category
            # bundle is also self-confounded (can't attribute among its own cats).
            external = self._confounders(by_campaign[(b["acct"], b["cid"])], b)
            self_confounded = (not b["known"]) and len(b["cats"]) > 1
            confounded = bool(external) or self_confounded

            outcome, magnitude, detail, metric, pre_val, post_val = self._evaluate_outcome(pre, post)

            # Phase 2.3 — trend-adjust attributable (non-confounded) episodes whose
            # metric is above a floor (near-$0 CPA / near-0 CVR make % math explode).
            ta = {"trend_adjusted": False, "trend_slope": 0.0, "expected_value": 0.0,
                  "raw_magnitude": magnitude, "adjusted_magnitude": magnitude,
                  "trend_contribution_pct": 0.0}
            floor = {"cpa": 1.0, "cvr": 0.005}.get(metric, 0.0)
            if not confounded and metric and pre_val >= floor and post_val >= floor:
                adj_oc, adj_mag, raw_mag, slope, expected, trend_pct = self._trend_adjust(
                    b, metric, pre_val, post_val)
                ta = {"trend_adjusted": True, "trend_slope": slope, "expected_value": expected,
                      "raw_magnitude": raw_mag, "adjusted_magnitude": adj_mag,
                      "trend_contribution_pct": trend_pct}
                if slope and adj_oc != outcome:
                    detail += (f" → trend-adjusted to {adj_oc.value} "
                               f"(~{trend_pct:.0%} of the move was pre-existing trend)")
                outcome, magnitude = adj_oc, adj_mag

            if confounded:
                outcome = EpisodeOutcome.CONFOUNDED

            cat_label = self._bundle_label(b)
            scope = "campaign" if b["cid"] else "account"
            frame = self._confidence(b, cat_label, scope, pre, post, detail,
                                     external, self_confounded)

            ep = Episode(
                episode_id=uuid.uuid4().hex[:12],
                account_id=b["acct"],
                change_event_id=b["rep_id"] or "",
                campaign_id=b["cid"],
                change_description=f"{b['cnt']}x {cat_label} ({b['actor']}) on {b['cdate']}",
                domain=self._infer_domain(b["label"], b["cats"]),
                change_category=b["label"],
                change_count=b["cnt"],
                actor=b["actor"],
                confounded=confounded,
                pre_metrics=pre,
                post_metrics=post,
                outcome=outcome,
                outcome_magnitude=magnitude,
                outcome_detail=detail,
                confidence_tier=frame[0],
                what_we_know=frame[1],
                what_we_cant_rule_out=frame[2],
                check_next=frame[3],
                trend_adjusted=ta["trend_adjusted"],
                trend_slope=ta["trend_slope"],
                expected_value=ta["expected_value"],
                raw_magnitude=ta["raw_magnitude"],
                adjusted_magnitude=ta["adjusted_magnitude"],
                trend_contribution_pct=ta["trend_contribution_pct"],
                recorded_at=datetime.now(timezone.utc),
            )
            self.repo.insert_episode(ep)
            episodes.append(ep)
        # Checkpoint so separate reader connections see a consistent state
        # (avoids cross-process WAL-visibility flakiness on the boolean column).
        try:
            self.db.execute("CHECKPOINT")
        except Exception:
            pass
        return episodes

    def process_pending_episodes(self) -> list[Episode]:
        return self.process_episodes(reset=True)

    def _confounders(self, campaign_bundles: list[dict], b: dict) -> list[str]:
        """Other actions in this bundle's post-window that pull a DIFFERENT lever
        than this bundle did. A repeat of the same category (e.g. another budget
        tweak two days later) is the same lever — it reinforces the attribution,
        it doesn't confound it. Only a category OUTSIDE this bundle's own set
        breaks single-cause attribution. The confounding actor is noted because
        'confounded by another auto-apply' vs 'by a human' are different (Finding 3)."""
        out = []
        for other in campaign_bundles:
            if other is b:
                continue
            if not (b["cdate"] <= other["cdate"] < b["cdate"] + timedelta(days=POST_WINDOW_DAYS)):
                continue
            new_levers = other["cats"] - b["cats"]
            if new_levers:
                out.append(f"{other['actor']} {'+'.join(sorted(new_levers))} on {other['cdate']}")
        return out

    def _bundle_label(self, b: dict) -> str:
        if bsig.is_bundle(b["label"]):
            return b["label"]
        if b["known"]:
            return tax.label(b["label"])  # single category -> friendly phrase
        return "+".join(sorted(b["cats"])) + " (unclassified bundle)"

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

    def _evaluate_outcome(self, pre: dict, post: dict):
        """Returns (outcome, magnitude, detail, metric, pre_val, post_val).
        metric/pre_val/post_val identify the primary metric so 2.3 can
        trend-adjust the same one. metric is None when no outcome is readable."""
        if not pre.get("conversions") or not post.get("conversions"):
            return EpisodeOutcome.NEUTRAL, 0.0, "Insufficient conversion data to read an outcome", None, 0, 0
        pre_cpa, post_cpa = pre.get("cpa", 0), post.get("cpa", 0)
        if pre_cpa and post_cpa:
            d = (post_cpa - pre_cpa) / pre_cpa
            detail = f"CPA ${pre_cpa:.0f}→${post_cpa:.0f} ({d:+.0%})"
            oc = (EpisodeOutcome.IMPROVED if d < -0.10 else
                  EpisodeOutcome.DEGRADED if d > 0.10 else EpisodeOutcome.NEUTRAL)
            return oc, abs(d), detail, "cpa", pre_cpa, post_cpa
        pre_cvr, post_cvr = pre.get("cvr", 0), post.get("cvr", 0)
        if pre_cvr and post_cvr:
            d = (post_cvr - pre_cvr) / pre_cvr
            detail = f"CVR {pre_cvr:.1%}→{post_cvr:.1%} ({d:+.0%})"
            oc = (EpisodeOutcome.IMPROVED if d > 0.10 else
                  EpisodeOutcome.DEGRADED if d < -0.10 else EpisodeOutcome.NEUTRAL)
            return oc, abs(d), detail, "cvr", pre_cvr, post_cvr
        return EpisodeOutcome.NEUTRAL, 0.0, "No material CPA/CVR movement", None, 0, 0

    def _pre_trend_slope(self, account_id: str, campaign_id: str, metric: str,
                         change_date: date, lookback: int = 14) -> float:
        """OLS daily slope of the metric over the `lookback` days before the change
        — but ONLY if that pre-trend is statistically real (significant and
        directional). A noisy/flat pre-window returns 0, so we never subtract a
        trend we don't actually believe (which would amplify noise, not remove it)."""
        from brightmatter.analysis.trends import compute_trend
        start = change_date - timedelta(days=lookback)
        cf = "AND campaign_id = ?" if campaign_id else ""
        params: list[Any] = [account_id]
        if campaign_id:
            params.append(campaign_id)
        params += [start, change_date]
        rows = self.db.fetchall(f"""
            SELECT date, impressions, clicks, cost_micros/1000000.0, conversions, conversion_value
            FROM daily_metrics WHERE account_id = ? {cf} AND date >= ? AND date < ?
            ORDER BY date
        """, params)
        pts = []
        for d, imp, clk, cost, conv, val in rows:
            if metric == "cpa":
                v = (cost / conv) if conv else None
            elif metric == "cvr":
                v = (conv / clk) if clk else None
            else:
                v = None
            if v is not None:
                pts.append((d, v))
        if len(pts) < 5:
            return 0.0
        t = compute_trend([d for d, _ in pts], [v for _, v in pts], metric)
        if t is None or t.classification not in ("improving", "declining", "rising", "falling"):
            return 0.0  # no significant directional pre-trend -> no adjustment
        return t.slope

    def _trend_adjust(self, b: dict, metric: str, pre_val: float, post_val: float):
        """Project where the metric would be sans change, isolate the change's
        contribution. Returns (outcome, adj_mag, raw_mag, slope, expected, trend_pct)."""
        slope = self._pre_trend_slope(b["acct"], b["cid"], metric, b["cdate"])
        expected = pre_val + slope * POST_WINDOW_DAYS
        raw_pct = (post_val - pre_val) / pre_val if pre_val else 0.0
        adj_pct = (post_val - expected) / pre_val if pre_val else 0.0
        # Fraction of the raw move explained by the pre-existing trend, clamped to
        # [0,1] (a trend explaining >100% or reversing the move isn't a clean share).
        raw_move = post_val - pre_val
        trend_pct = ((expected - pre_val) / raw_move) if abs(raw_move) > 1e-9 else 0.0
        trend_pct = max(0.0, min(1.0, trend_pct))
        fav = -1 if metric == "cpa" else 1   # favorable-direction sign
        adj_favorable = adj_pct * fav        # >0 = improvement net of trend
        if abs(adj_pct) < 0.05:
            oc = EpisodeOutcome.NEUTRAL
        elif adj_favorable > 0.10:
            oc = EpisodeOutcome.IMPROVED
        elif adj_favorable < -0.10:
            oc = EpisodeOutcome.DEGRADED
        else:
            oc = EpisodeOutcome.NEUTRAL
        return oc, abs(adj_pct), abs(raw_pct), slope, expected, trend_pct

    def _confidence(self, b: dict, cat_label: str, scope: str, pre: dict, post: dict,
                    detail: str, external: list[str],
                    self_confounded: bool) -> tuple[str, str, str, str]:
        where = f"campaign {b['cid']}" if b["cid"] else "the account"
        know = (f"{b['cnt']} change(s) — {cat_label} ({b['actor']}) — on {where} on {b['cdate']}. {detail}. "
                f"Pre {PRE_WINDOW_DAYS}d: CPA ${pre['cpa']:.0f}, CVR {pre['cvr']:.1%}, {pre['conversions']:.0f} conv; "
                f"post {POST_WINDOW_DAYS}d: CPA ${post['cpa']:.0f}, CVR {post['cvr']:.1%}, {post['conversions']:.0f} conv.")
        cant = ["the metric may already have been trending before the change "
                "(no trend adjustment applied — that's Phase 2)",
                "seasonal demand or competitor shifts in the same window"]
        if self_confounded:
            cant.insert(0, "this is an unclassified multi-category change — the effect can't be "
                           "attributed to any single lever within it")
        if external:
            cant.insert(0, f"other actions hit the same {scope} in the window "
                           f"({'; '.join(external[:3])}{'…' if len(external) > 3 else ''})")
        cant_s = "Can't rule out: " + "; ".join(cant) + "."
        check = (f"Was CPA/CVR already moving before {b['cdate']}? "
                 + ("Separate the overlapping actions noted above. " if external else "")
                 + "Trend-adjusted attribution comes in Phase 2.")
        tier = "CONFIRMED" if (not external and not self_confounded
                               and detail.startswith("No material")) else "SUGGESTIVE"
        return tier, know, cant_s, check

    def _infer_domain(self, label: str, cats: frozenset[str]) -> str:
        if "budget" in label or "budget" in cats or "bidding" in label:
            return "bidding_strategy"
        if "targeting" in label or "targeting_keyword" in cats:
            return "non_branded_search"
        if "creative" in label or "asset" in label or {"ad_creative", "asset"} & cats:
            return "creative"
        return "campaign_structure"
