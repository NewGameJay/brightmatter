"""
BrightMatter Cron Worker

Three-tier data ingestion + learning pipeline:
    Tier 1 — Ingest signals from shared Supabase (MH-OS Trigger.dev output)
    Tier 2 — Ingest daily spend deltas from BigQuery (when credentials available)
    Tier 3 — Publish high-confidence patterns to Airtable (when credentials available)

Plus: pull events, process through learning pipeline, consolidate,
refresh guidance cache.

Run modes:
    python worker.py                     # single cycle
    python worker.py --loop --interval 900  # continuous (every 15 min)

Requires:
    SUPABASE_URL      — Supabase project URL
    SUPABASE_KEY      — Supabase service role key
Optional:
    BIGQUERY_CREDENTIALS_JSON — enables Tier 2 (BQ daily delta)
    AIRTABLE_API_KEY          — enables Tier 3 (pattern publishing)
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("brightmatter.worker")

LEVER_TO_DOMAIN = {
    "Lead Volume": "campaign",
    "Conversion Rate": "campaign",
    "Pipeline": "revenue",
    "Revenue": "revenue",
    "Retention": "health",
    "Churn": "health",
    "Content": "content",
    "All": "generic",
}


class BrightMatterWorker:
    """Pulls events from Supabase, processes through learning pipeline, updates guidance."""

    def __init__(self):
        from lib.intelligence import IntelligenceEngine
        from lib.intelligence_bridge import IntelligenceBridge

        self.engine = IntelligenceEngine()
        self.bridge = IntelligenceBridge(engine=self.engine)
        self._supabase = None

    @property
    def supabase(self):
        if self._supabase is None:
            from lib.supabase_client import get_supabase
            self._supabase = get_supabase()
        return self._supabase

    def run_cycle(self) -> Dict[str, Any]:
        """Run one full processing cycle with all three tiers."""
        stats = {
            "events_pulled": 0,
            "events_processed": 0,
            "events_failed": 0,
            "signals_ingested": 0,
            "bq_episodes": 0,
            "patterns_published": 0,
            "guidance_refreshed": 0,
            "consolidation": {},
        }

        try:
            # ── Tier 1: Ingest signals from shared Supabase ──────────
            try:
                sig_stats = self._ingest_signals()
                stats["signals_ingested"] = sig_stats.get("ingested", 0)
                logger.info(f"Tier 1 signals: {sig_stats}")
            except Exception as e:
                logger.error(f"Tier 1 signal ingestion failed: {e}")

            # ── Tier 2: Ingest daily BQ delta (if credentials available) ─
            try:
                bq_stats = self._ingest_bq_delta()
                stats["bq_episodes"] = bq_stats.get("episodes_created", 0)
                logger.info(f"Tier 2 BQ delta: {bq_stats}")
            except Exception as e:
                logger.debug(f"Tier 2 BQ ingestion skipped or failed: {e}")

            # ── Standard event processing ────────────────────────────
            new_events = self._pull_new_events()
            stats["events_pulled"] = len(new_events)
            logger.info(f"Pulled {len(new_events)} new events from Supabase")

            for event in new_events:
                try:
                    self._process_event(event)
                    stats["events_processed"] += 1

                    self.supabase.table("events").update(
                        {"processed_by_bm": True}
                    ).eq("id", event["id"]).execute()
                except Exception as e:
                    logger.error(f"Failed to process event {event.get('id')}: {e}")
                    stats["events_failed"] += 1

            # ── Consolidation ────────────────────────────────────────
            consolidation_stats = self.engine.run_consolidation()
            stats["consolidation"] = consolidation_stats
            logger.info(f"Consolidation: {consolidation_stats}")

            # ── Checkpoint processing ────────────────────────────────
            try:
                from lib.intelligence.outcomes.checkpoint_processor import CheckpointProcessor
                processor = CheckpointProcessor(self.engine.storage, self.bridge)
                checkpoint_stats = processor.process_all_due()
                stats["checkpoints"] = checkpoint_stats
            except Exception as e:
                logger.error(f"Checkpoint processing failed: {e}")

            # ── Tier 3: Publish patterns to Airtable ─────────────────
            try:
                pub_stats = self._publish_patterns_to_airtable()
                stats["patterns_published"] = pub_stats.get("published", 0)
                logger.info(f"Tier 3 Airtable publish: {pub_stats}")
            except Exception as e:
                logger.debug(f"Tier 3 Airtable publish skipped or failed: {e}")

            # ── Refresh guidance cache ───────────────────────────────
            refreshed = self._refresh_guidance_cache()
            stats["guidance_refreshed"] = refreshed
            logger.info(f"Guidance cache refreshed for {refreshed} pairs")

        except Exception as e:
            logger.error(f"Worker cycle failed: {e}")
            stats["error"] = str(e)

        return stats

    def _pull_new_events(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Pull unprocessed events from Supabase."""
        result = (
            self.supabase.table("events")
            .select("*")
            .eq("processed_by_bm", False)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data or []

    def _process_event(self, event: Dict[str, Any]):
        """Route event to appropriate handler."""
        event_type = event.get("event_type", "")

        if event_type == "signal":
            self._process_signal(event)
        elif event_type == "skill_completed":
            self._process_skill_completion(event)
        elif event_type == "plan_completed":
            self._process_plan_completion(event)
        elif event_type == "human_feedback":
            self._process_feedback(event)
        elif event_type == "expert_override":
            self._process_expert_override(event)
        else:
            logger.warning(f"Unknown event_type: {event_type}")

    def _process_signal(self, event: Dict[str, Any]):
        """Convert a signal event (e.g., from MH-OS) into an episode."""
        from lib.intelligence.types import (
            Domain, EpisodicMemory, Prediction, Outcome, EpisodeSource,
        )
        import uuid

        skill_name = event.get("skill_name") or event.get("source", "signal")
        client_id = event.get("client_id", "unknown")
        domain_str = event.get("domain", "generic")

        try:
            domain = Domain(domain_str)
        except ValueError:
            domain = Domain.GENERIC

        metrics = event.get("metrics", {})
        context = event.get("context", {})

        primary_signal = 0.5
        for key in ["primary_metric", "value", "signal", "score"]:
            if key in metrics and isinstance(metrics[key], (int, float)):
                primary_signal = float(metrics[key])
                break

        prediction = Prediction(
            prediction_id=str(uuid.uuid4())[:12],
            skill_name=skill_name,
            tenant_id=client_id,
            domain=domain,
            expected_signal=0.5,
            expected_baseline=1.0,
            context=context,
        )

        outcome = Outcome(
            prediction_id=prediction.prediction_id,
            observed_signal=primary_signal,
            observed_baseline=1.0,
            goal_completed=primary_signal > 0.5,
            metadata={
                "_source": event.get("source", ""),
                "_event_id": event.get("id", ""),
                "_episode_source": EpisodeSource.MARKET_OBSERVATION.value,
                **metrics,
            },
        )

        episode = EpisodicMemory(
            prediction=prediction,
            outcome=outcome,
        )
        self.engine.episodic.store(episode)

    def _process_skill_completion(self, event: Dict[str, Any]):
        """Process a completed skill execution event."""
        skill_name = event.get("skill_name", "")
        client_id = event.get("client_id", "")
        result = event.get("result", {})
        metrics = event.get("metrics", {})
        context = event.get("context", {})

        guidance = self.bridge.get_skill_guidance(
            skill_name=skill_name,
            client_id=client_id,
            inputs=context,
        )

        tracking_id = self.bridge.start_tracking(
            skill_name=skill_name,
            client_id=client_id,
            guidance=guidance,
            context=context,
        )

        self.bridge.complete_tracking(
            tracking_id=tracking_id,
            result=result,
            metrics=metrics,
            deferred=True,
        )

    def _process_plan_completion(self, event: Dict[str, Any]):
        """Process a completed plan/module execution event."""
        module_id = event.get("skill_name", "") or event.get("module_id", "")
        client_id = event.get("client_id", "")
        execution_data = event.get("result", {})

        self.bridge.consolidate_from_module(
            module_id=module_id,
            client_id=client_id,
            execution_data=execution_data,
        )

    def _process_feedback(self, event: Dict[str, Any]):
        """Process human feedback on a prediction."""
        result = event.get("result", {})
        prediction_id = result.get("prediction_id", "")
        rating = result.get("rating", 0.5)

        if prediction_id:
            self.engine.record_user_feedback(
                prediction_id=prediction_id,
                user_rating=float(rating),
                user_correction=result.get("correction"),
            )

    def _process_expert_override(self, event: Dict[str, Any]):
        """Process an expert override — highest-value learning signal.

        When a marketer rejects generated output and writes their own,
        this is the strongest signal about what the right answer looks like.
        """
        from lib.intelligence.types import (
            Domain, EpisodicMemory, Prediction, Outcome, EpisodeSource,
        )
        import uuid

        skill_name = event.get("skill_name", "")
        client_id = event.get("client_id", "")
        result = event.get("result", {})
        context = event.get("context", {})
        domain_str = event.get("domain", "generic")

        try:
            domain = Domain(domain_str)
        except ValueError:
            domain = Domain.GENERIC

        prediction = Prediction(
            prediction_id=str(uuid.uuid4())[:12],
            skill_name=skill_name,
            tenant_id=client_id,
            domain=domain,
            expected_signal=0.5,
            expected_baseline=1.0,
            context=context,
        )

        outcome = Outcome(
            prediction_id=prediction.prediction_id,
            observed_signal=1.0,
            observed_baseline=1.0,
            goal_completed=True,
            business_impact=0.0,
            metadata={
                "_source": "expert_override",
                "_episode_source": EpisodeSource.OPERATOR_FEEDBACK.value,
                "_event_id": event.get("id", ""),
                "_expert_output": result.get("expert_output", ""),
                "_original_output": result.get("original_output", ""),
                "_override_reason": result.get("reason", ""),
            },
        )

        episode = EpisodicMemory(
            prediction=prediction,
            outcome=outcome,
            weight=2.0,
        )
        self.engine.episodic.store(episode)

    # ── Tier 1: Signal Ingestion ───────────────────────────────────

    def _ingest_signals(self, limit: int = 200) -> Dict[str, Any]:
        """Poll the shared `signals` table for rows not yet ingested.

        Uses bm_watermarks to track the last processed signal timestamp
        so we never re-process rows. Each signal becomes an episodic memory.
        """
        stats = {"checked": 0, "ingested": 0, "skipped": 0}

        watermark = self._get_watermark("signals")
        last_ts = watermark.get("last_processed_at") if watermark else None

        query = (
            self.supabase.table("signals")
            .select("*")
            .order("created_at", desc=False)
            .limit(limit)
        )
        if last_ts:
            query = query.gt("created_at", last_ts)

        result = query.execute()
        rows = result.data or []
        stats["checked"] = len(rows)

        if not rows:
            return stats

        from lib.intelligence.types import (
            Domain, EpisodicMemory, Prediction, Outcome, EpisodeSource,
        )

        latest_ts = last_ts
        for row in rows:
            signal_id = row.get("id", "")
            source = row.get("source", "signal")
            lever = row.get("lever", "All")
            metrics = row.get("metrics") or {}
            dt = row.get("date", "")

            domain_str = LEVER_TO_DOMAIN.get(lever, "generic")
            try:
                domain = Domain(domain_str)
            except ValueError:
                domain = Domain.GENERIC

            primary_signal = 0.5
            for key in ["primary_metric", "value", "signal", "score"]:
                if key in metrics and isinstance(metrics[key], (int, float)):
                    primary_signal = float(metrics[key])
                    break

            ep_hash = hashlib.md5(f"sig-{signal_id}".encode()).hexdigest()[:12]
            episode_id = f"ep-sig-{ep_hash}"

            prediction = Prediction(
                prediction_id=episode_id,
                skill_name=source,
                tenant_id="marketerhire",
                domain=domain,
                expected_signal=0.5,
                expected_baseline=1.0,
                context={
                    "lever": lever,
                    "cadence": row.get("cadence", ""),
                    "date": dt,
                    "summary": row.get("summary", "")[:200],
                    "source": "mh-os-signal",
                },
            )

            outcome = Outcome(
                prediction_id=episode_id,
                observed_signal=primary_signal,
                observed_baseline=1.0,
                goal_completed=primary_signal > 0.5,
                metadata={
                    "_source": source,
                    "_signal_id": signal_id,
                    "_episode_source": EpisodeSource.MARKET_OBSERVATION.value,
                    **metrics,
                },
            )

            episode = EpisodicMemory(prediction=prediction, outcome=outcome)
            try:
                self.engine.episodic.store(episode)
                stats["ingested"] += 1
            except Exception as e:
                logger.warning(f"Failed to store signal episode {episode_id}: {e}")
                stats["skipped"] += 1

            row_ts = row.get("created_at", "")
            if row_ts and (not latest_ts or row_ts > latest_ts):
                latest_ts = row_ts

        if latest_ts:
            self._set_watermark("signals", last_processed_at=latest_ts)

        return stats

    # ── Tier 2: BigQuery Daily Delta ─────────────────────────────

    def _ingest_bq_delta(self) -> Dict[str, Any]:
        """Pull yesterday's spend data from BigQuery and create episodes.

        Only runs if BIGQUERY_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS
        is set. Uses bm_watermarks to track last ingested date.
        """
        if not (
            os.environ.get("BIGQUERY_CREDENTIALS_JSON")
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        ):
            return {"skipped": True, "reason": "no BQ credentials"}

        from lib.bigquery_client import get_bq_client
        from lib.intelligence.types import (
            Domain, EpisodicMemory, Prediction, Outcome, EpisodeSource,
        )

        stats = {"episodes_created": 0, "episodes_skipped": 0}

        watermark = self._get_watermark("bigquery")
        last_date_str = None
        if watermark and watermark.get("metadata"):
            last_date_str = watermark["metadata"].get("last_date")

        if last_date_str:
            start = (
                datetime.fromisoformat(last_date_str) + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        else:
            start = (date.today() - timedelta(days=1)).isoformat()

        end = date.today().isoformat()

        if start >= end:
            return {"skipped": True, "reason": "already up to date"}

        bq = get_bq_client()
        rows = bq.query_daily_spend(start, end)

        prior_cpa_by_channel: Dict[str, float] = {}

        for row in rows:
            channel = row.get("channel", "unknown")
            dt = row.get("dt")
            dt_str = dt.isoformat()[:10] if hasattr(dt, "isoformat") else str(dt)[:10]

            spend = float(row.get("spend", 0))
            appt = float(row.get("nbr_appt", 0))
            cpa = spend / appt if appt > 0 else 0

            prior_cpa = prior_cpa_by_channel.get(channel, cpa)

            ep_raw = f"bq-daily-{channel}-{dt_str}"
            ep_hash = hashlib.md5(ep_raw.encode()).hexdigest()[:12]
            episode_id = f"ep-bq-{ep_hash}"

            prediction = Prediction(
                prediction_id=episode_id,
                skill_name="channel-spend-daily",
                tenant_id="marketerhire",
                domain=Domain.CAMPAIGN,
                expected_signal=prior_cpa if prior_cpa else 0.5,
                expected_baseline=1.0,
                context={
                    "channel": channel,
                    "date": dt_str,
                    "window": "daily",
                    "source": "bigquery-delta",
                },
            )

            outcome = Outcome(
                prediction_id=episode_id,
                observed_signal=cpa if cpa else 0.5,
                observed_baseline=1.0,
                goal_completed=cpa < prior_cpa if prior_cpa else False,
                metadata={
                    "_source": "bigquery-delta",
                    "_episode_source": EpisodeSource.MARKET_OBSERVATION.value,
                    "spend": spend,
                    "ff": float(row.get("nbr_ff", 0)),
                    "appt": appt,
                    "mql": float(row.get("nbr_mql", 0)),
                    "sql_leads": float(row.get("nbr_sql", 0)),
                    "cs": float(row.get("nbr_cs", 0)),
                    "cpa": cpa,
                },
            )

            episode = EpisodicMemory(prediction=prediction, outcome=outcome)
            try:
                self.engine.episodic.store(episode)
                stats["episodes_created"] += 1
            except Exception as e:
                logger.warning(f"BQ episode {episode_id} failed: {e}")
                stats["episodes_skipped"] += 1

            prior_cpa_by_channel[channel] = cpa

        if rows:
            last_dt = rows[-1].get("dt")
            last_dt_str = (
                last_dt.isoformat()[:10]
                if hasattr(last_dt, "isoformat")
                else str(last_dt)[:10]
            )
            self._set_watermark(
                "bigquery",
                last_processed_at=datetime.now(timezone.utc).isoformat(),
                metadata={"last_date": last_dt_str},
            )

        return stats

    # ── Tier 3: Airtable Pattern Publishing ──────────────────────

    def _publish_patterns_to_airtable(self) -> Dict[str, Any]:
        """Push high-confidence patterns to Airtable after consolidation.

        Only runs if AIRTABLE_API_KEY is set. Publishes patterns with
        confidence >= 0.7 and evidence_count >= 3.
        """
        if not os.environ.get("AIRTABLE_API_KEY"):
            return {"skipped": True, "reason": "no AIRTABLE_API_KEY"}

        result = (
            self.supabase.table("semantic_patterns")
            .select("*")
            .gte("confidence", 0.7)
            .gte("evidence_count", 3)
            .is_("archived_at", "null")
            .execute()
        )
        patterns = result.data or []

        if not patterns:
            return {"total": 0, "published": 0, "reason": "no qualifying patterns"}

        watermark = self._get_watermark("airtable-publish")
        last_publish = watermark.get("last_processed_at") if watermark else None

        if last_publish:
            fresh_patterns = [
                p for p in patterns
                if (p.get("updated_at") or "") > last_publish
            ]
        else:
            fresh_patterns = patterns

        if not fresh_patterns:
            return {"total": len(patterns), "published": 0, "reason": "no new patterns since last publish"}

        from lib.airtable_publisher import AirtablePublisher
        publisher = AirtablePublisher()
        pub_stats = publisher.publish_as_recommendations(fresh_patterns)

        if pub_stats.get("published", 0) > 0:
            self._set_watermark(
                "airtable-publish",
                last_processed_at=datetime.now(timezone.utc).isoformat(),
            )

        return pub_stats

    # ── Watermark Helpers ────────────────────────────────────────

    def _get_watermark(self, source: str) -> Optional[Dict[str, Any]]:
        """Read the watermark for a given source from bm_watermarks."""
        try:
            result = (
                self.supabase.table("bm_watermarks")
                .select("*")
                .eq("source", source)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as e:
            logger.debug(f"Watermark read failed for {source}: {e}")
            return None

    def _set_watermark(
        self,
        source: str,
        last_processed_id: Optional[str] = None,
        last_processed_at: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """Upsert a watermark for a given source."""
        row: Dict[str, Any] = {
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if last_processed_id is not None:
            row["last_processed_id"] = last_processed_id
        if last_processed_at is not None:
            row["last_processed_at"] = last_processed_at
        if metadata is not None:
            row["metadata"] = metadata

        try:
            self.supabase.table("bm_watermarks").upsert(
                row, on_conflict="source"
            ).execute()
        except Exception as e:
            logger.warning(f"Watermark write failed for {source}: {e}")

    # ── Guidance Cache ───────────────────────────────────────────

    def _refresh_guidance_cache(self) -> int:
        """Recompute guidance for active (skill, client) pairs."""
        pairs = self._get_active_skill_client_pairs()
        refreshed = 0

        for skill_name, client_id in pairs:
            try:
                from lib.intelligence.types import Domain as DomainEnum
                domain_str = self.bridge.get_domain_name(skill_name)
                try:
                    domain = DomainEnum(domain_str)
                except ValueError:
                    domain = DomainEnum.GENERIC

                guidance = self.engine.get_guidance(
                    skill_name=skill_name,
                    tenant_id=client_id,
                    domain=domain,
                )

                guidance_dict = guidance.to_dict() if hasattr(guidance, "to_dict") else {}

                self.supabase.table("guidance_cache").upsert({
                    "skill_name": skill_name,
                    "client_id": client_id,
                    "domain": domain_str,
                    "parameters": guidance_dict.get("parameters", {}),
                    "confidence": guidance_dict.get("confidence", 0.5),
                    "expected_value": guidance_dict.get("pattern_expected_value"),
                    "is_exploration": guidance_dict.get("is_exploration", True),
                    "patterns_used": guidance_dict.get("patterns_used", []),
                    "predicted_outcome": guidance_dict.get("predicted_outcome"),
                    "predicted_baseline": guidance_dict.get("predicted_baseline"),
                    "pattern_expected_value": guidance_dict.get("pattern_expected_value"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).execute()

                refreshed += 1
            except Exception as e:
                logger.debug(f"Failed to refresh guidance for {skill_name}/{client_id}: {e}")

        return refreshed

    def _get_active_skill_client_pairs(self) -> List[tuple]:
        """Get recently active (skill_name, client_id) pairs from events."""
        try:
            result = (
                self.supabase.rpc(
                    "get_active_pairs",
                    {"lookback_days": 30},
                ).execute()
            )
            if result.data:
                return [(r["skill_name"], r["client_id"]) for r in result.data]
        except Exception:
            pass

        # Fallback: query events directly
        try:
            result = (
                self.supabase.table("events")
                .select("skill_name, client_id")
                .neq("skill_name", None)
                .order("created_at", desc=True)
                .limit(200)
                .execute()
            )
            pairs = set()
            for row in (result.data or []):
                sn = row.get("skill_name")
                ci = row.get("client_id")
                if sn and ci:
                    pairs.add((sn, ci))
            return list(pairs)
        except Exception as e:
            logger.warning(f"Could not get active pairs: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(description="BrightMatter cron worker")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=900, help="Seconds between cycles (default 15 min)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    worker = BrightMatterWorker()

    if args.loop:
        logger.info(f"Starting continuous worker (interval={args.interval}s)")
        while True:
            try:
                stats = worker.run_cycle()
                logger.info(f"Cycle complete: {stats}")
            except Exception as e:
                logger.error(f"Cycle error: {e}")
            time.sleep(args.interval)
    else:
        stats = worker.run_cycle()
        logger.info(f"Single cycle complete: {stats}")
        return stats


if __name__ == "__main__":
    main()
