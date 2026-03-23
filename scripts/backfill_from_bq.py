"""
BrightMatter BigQuery Historical Backfill

Queries MH-OS BigQuery warehouse for historical ad spend data and
creates episodic memories so BrightMatter can learn long-term patterns.

Usage:
    python scripts/backfill_from_bq.py                        # last 2 years, weekly
    python scripts/backfill_from_bq.py --start 2023-01-01     # custom start
    python scripts/backfill_from_bq.py --granularity daily    # daily episodes
    python scripts/backfill_from_bq.py --dry-run              # preview without writing

Requires:
    BIGQUERY_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS
    SUPABASE_URL + SUPABASE_KEY
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("brightmatter.backfill.bq")

TENANT_ID = "marketerhire"


def _episode_id(channel: str, window_start: str, granularity: str) -> str:
    """Deterministic episode ID from (channel, date, granularity) so re-runs are idempotent."""
    raw = f"bq-{granularity}-{channel}-{window_start}"
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"ep-bq-{h}"


def _compute_deltas(
    current: Dict[str, float], prior: Dict[str, float]
) -> Dict[str, float]:
    """Compute WoW or MoM percentage changes."""
    deltas = {}
    for key in current:
        cur = current.get(key, 0)
        prev = prior.get(key, 0)
        if prev and prev != 0:
            deltas[f"{key}_delta_pct"] = round((cur - prev) / abs(prev) * 100, 2)
        else:
            deltas[f"{key}_delta_pct"] = 0
    return deltas


def backfill_weekly(
    start_date: str,
    end_date: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill weekly channel summaries as episodic memories."""
    from lib.bigquery_client import get_bq_client
    from lib.intelligence import IntelligenceEngine
    from lib.intelligence.types import (
        Domain, EpisodicMemory, EpisodeSource, Prediction, Outcome,
    )
    import uuid

    bq = get_bq_client()
    engine = IntelligenceEngine()

    logger.info(f"Querying weekly channel summaries {start_date} → {end_date}")
    rows = bq.query_weekly_channel_summary(start_date, end_date)
    logger.info(f"Got {len(rows)} weekly channel rows from BigQuery")

    by_channel: Dict[str, List[Dict]] = {}
    for row in rows:
        ch = row.get("channel", "unknown")
        by_channel.setdefault(ch, []).append(row)

    stats = {"channels": 0, "episodes_created": 0, "episodes_skipped": 0}

    for channel, channel_rows in sorted(by_channel.items()):
        stats["channels"] += 1
        prior_row = None

        for row in channel_rows:
            week_start = row.get("week_start")
            if hasattr(week_start, "isoformat"):
                week_start = week_start.isoformat()[:10]
            else:
                week_start = str(week_start)[:10]

            episode_id = _episode_id(channel, week_start, "weekly")

            current_metrics = {
                "spend": float(row.get("total_spend", 0)),
                "ff": float(row.get("total_ff", 0)),
                "appt": float(row.get("total_appt", 0)),
                "cs": float(row.get("total_cs", 0)),
                "deal_value": float(row.get("total_deal_value", 0)),
                "cpa": float(row.get("cpa", 0) or 0),
                "cac": float(row.get("cac", 0) or 0),
            }

            if prior_row:
                prior_metrics = {
                    "spend": float(prior_row.get("total_spend", 0)),
                    "ff": float(prior_row.get("total_ff", 0)),
                    "appt": float(prior_row.get("total_appt", 0)),
                    "cs": float(prior_row.get("total_cs", 0)),
                    "deal_value": float(prior_row.get("total_deal_value", 0)),
                    "cpa": float(prior_row.get("cpa", 0) or 0),
                    "cac": float(prior_row.get("cac", 0) or 0),
                }
                prior_cpa = prior_metrics["cpa"]
                deltas = _compute_deltas(current_metrics, prior_metrics)
            else:
                prior_cpa = current_metrics["cpa"]
                deltas = {}

            if dry_run:
                logger.info(
                    f"[DRY RUN] {episode_id} | {channel} | {week_start} | "
                    f"spend=${current_metrics['spend']:.0f} cpa=${current_metrics['cpa']:.2f}"
                )
                stats["episodes_skipped"] += 1
                prior_row = row
                continue

            prediction = Prediction(
                prediction_id=episode_id,
                skill_name="channel-spend-weekly",
                tenant_id=TENANT_ID,
                domain=Domain.CAMPAIGN,
                expected_signal=prior_cpa if prior_cpa else 0.5,
                expected_baseline=1.0,
                context={
                    "channel": channel,
                    "week_start": week_start,
                    "window": "weekly",
                    "source": "bigquery-backfill",
                },
            )

            cpa = current_metrics["cpa"]
            goal_completed = cpa < prior_cpa if prior_cpa else False

            outcome = Outcome(
                prediction_id=episode_id,
                observed_signal=cpa if cpa else 0.5,
                observed_baseline=1.0,
                goal_completed=goal_completed,
                metadata={
                    "_source": "bigquery-backfill",
                    "_episode_source": EpisodeSource.MARKET_OBSERVATION.value,
                    **current_metrics,
                    **deltas,
                },
            )

            episode = EpisodicMemory(prediction=prediction, outcome=outcome)

            try:
                engine.episodic.store(episode)
                stats["episodes_created"] += 1
            except Exception as e:
                logger.warning(f"Failed to store episode {episode_id}: {e}")
                stats["episodes_skipped"] += 1

            prior_row = row

    return stats


def backfill_daily(
    start_date: str,
    end_date: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill daily channel spend as episodic memories."""
    from lib.bigquery_client import get_bq_client
    from lib.intelligence import IntelligenceEngine
    from lib.intelligence.types import (
        Domain, EpisodicMemory, EpisodeSource, Prediction, Outcome,
    )

    bq = get_bq_client()
    engine = IntelligenceEngine()

    logger.info(f"Querying daily spend {start_date} → {end_date}")
    rows = bq.query_daily_spend(start_date, end_date)
    logger.info(f"Got {len(rows)} daily rows from BigQuery")

    by_channel: Dict[str, List[Dict]] = {}
    for row in rows:
        ch = row.get("channel", "unknown")
        by_channel.setdefault(ch, []).append(row)

    stats = {"channels": 0, "episodes_created": 0, "episodes_skipped": 0}

    for channel, channel_rows in sorted(by_channel.items()):
        stats["channels"] += 1
        prior_row = None

        for row in channel_rows:
            dt = row.get("dt")
            if hasattr(dt, "isoformat"):
                dt_str = dt.isoformat()[:10]
            else:
                dt_str = str(dt)[:10]

            episode_id = _episode_id(channel, dt_str, "daily")

            spend = float(row.get("spend", 0))
            appt = float(row.get("nbr_appt", 0))
            cpa = spend / appt if appt > 0 else 0

            metrics = {
                "spend": spend,
                "ff": float(row.get("nbr_ff", 0)),
                "appt": appt,
                "mql": float(row.get("nbr_mql", 0)),
                "sql": float(row.get("nbr_sql", 0)),
                "cs": float(row.get("nbr_cs", 0)),
                "cpa": cpa,
            }

            prior_cpa = 0
            if prior_row:
                p_spend = float(prior_row.get("spend", 0))
                p_appt = float(prior_row.get("nbr_appt", 0))
                prior_cpa = p_spend / p_appt if p_appt > 0 else 0

            if dry_run:
                stats["episodes_skipped"] += 1
                prior_row = row
                continue

            prediction = Prediction(
                prediction_id=episode_id,
                skill_name="channel-spend-daily",
                tenant_id=TENANT_ID,
                domain=Domain.CAMPAIGN,
                expected_signal=prior_cpa if prior_cpa else 0.5,
                expected_baseline=1.0,
                context={
                    "channel": channel,
                    "date": dt_str,
                    "window": "daily",
                    "source": "bigquery-backfill",
                },
            )

            outcome = Outcome(
                prediction_id=episode_id,
                observed_signal=cpa if cpa else 0.5,
                observed_baseline=1.0,
                goal_completed=cpa < prior_cpa if prior_cpa else False,
                metadata={
                    "_source": "bigquery-backfill",
                    "_episode_source": EpisodeSource.MARKET_OBSERVATION.value,
                    **metrics,
                },
            )

            episode = EpisodicMemory(prediction=prediction, outcome=outcome)
            try:
                engine.episodic.store(episode)
                stats["episodes_created"] += 1
            except Exception as e:
                logger.warning(f"Failed to store episode {episode_id}: {e}")
                stats["episodes_skipped"] += 1

            prior_row = row

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill BrightMatter from BigQuery")
    parser.add_argument(
        "--start",
        default=(date.today() - timedelta(days=730)).isoformat(),
        help="Start date (default: 2 years ago)",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date (default: today)",
    )
    parser.add_argument(
        "--granularity",
        choices=["daily", "weekly"],
        default="weekly",
        help="Episode granularity (default: weekly)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(
        f"Backfill: {args.granularity} from {args.start} to {args.end}"
        + (" [DRY RUN]" if args.dry_run else "")
    )

    if args.granularity == "weekly":
        stats = backfill_weekly(args.start, args.end, dry_run=args.dry_run)
    else:
        stats = backfill_daily(args.start, args.end, dry_run=args.dry_run)

    logger.info(f"Backfill complete: {stats}")
    return stats


if __name__ == "__main__":
    main()
