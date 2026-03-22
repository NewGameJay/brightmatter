"""
BrightMatter Cron Worker

Pulls events from Supabase, processes through the learning pipeline,
and writes guidance back to the guidance_cache table.

Run modes:
    python worker.py                     # single cycle
    python worker.py --loop --interval 900  # continuous (every 15 min)

Requires:
    SUPABASE_URL      — Supabase project URL
    SUPABASE_KEY      — Supabase service role key
    FIREBASE_*        — Firebase credentials for BrightMatter engine
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("brightmatter.worker")


def _get_supabase():
    """Lazy-load Supabase client."""
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError("supabase package required: pip install supabase")
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)


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
            self._supabase = _get_supabase()
        return self._supabase

    def run_cycle(self) -> Dict[str, Any]:
        """Run one full processing cycle."""
        stats = {
            "events_pulled": 0,
            "events_processed": 0,
            "events_failed": 0,
            "guidance_refreshed": 0,
            "consolidation": {},
        }

        try:
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

            # Run consolidation
            consolidation_stats = self.engine.run_consolidation()
            stats["consolidation"] = consolidation_stats
            logger.info(f"Consolidation: {consolidation_stats}")

            # Run checkpoint processing
            try:
                from lib.intelligence.outcomes.checkpoint_processor import CheckpointProcessor
                processor = CheckpointProcessor(self.engine._firebase, self.bridge)
                checkpoint_stats = processor.process_all_due()
                stats["checkpoints"] = checkpoint_stats
            except Exception as e:
                logger.error(f"Checkpoint processing failed: {e}")

            # Refresh guidance cache
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
