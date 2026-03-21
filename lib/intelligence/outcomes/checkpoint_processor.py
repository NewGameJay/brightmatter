"""
Checkpoint Processor

Runs on a cron schedule. Finds pending outcomes that are due for
measurement (24h, 7d, or channel-specific intervals), collects
platform metrics using the delivery_metadata stored at tracking time,
and closes the deferred outcome to trigger learning.

Data sources (in priority order):
1. MH1HQ MCP — query execution results, report data
2. Platform APIs via delivery_metadata — campaign_id, ad_set_id
3. MH-OS signals (future) — BigQuery metrics, anomaly context
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .pending_store import PendingOutcome, PendingOutcomeStore

logger = logging.getLogger(__name__)


class CheckpointProcessor:
    """
    Processes due outcome checkpoints on a cron schedule.

    Queries PendingOutcomeStore for outcomes whose 24h or 7d windows have
    elapsed, collects metrics from available data sources, and closes the
    loop by calling bridge.close_deferred_outcome().
    """

    def __init__(self, firebase_client: Any, bridge: Any):
        self._store = PendingOutcomeStore(firebase_client)
        self._bridge = bridge
        self._firebase = firebase_client

    def process_all_due(self) -> Dict[str, Any]:
        """Process all due checkpoints. Called by cron."""
        results = {"processed": 0, "failed": 0, "skipped": 0, "details": []}

        for checkpoint_type in ["24h", "7d"]:
            due = self._store.query_due(checkpoint_type)
            logger.info(
                f"Checkpoint {checkpoint_type}: {len(due)} outcomes due"
            )

            for pending in due:
                try:
                    metrics = self._collect_metrics(pending)

                    if not metrics:
                        results["skipped"] += 1
                        results["details"].append({
                            "prediction_id": pending.prediction_id,
                            "action": "skipped",
                            "reason": "no_metrics_collected",
                        })
                        continue

                    classification = self._classify(
                        pending, metrics["primary_signal"]
                    )

                    self._bridge.close_deferred_outcome(
                        prediction_id=pending.prediction_id,
                        client_id=pending.client_id,
                        observed_signal=metrics["primary_signal"],
                        business_impact=metrics.get("business_impact", 0),
                        platform_metrics=metrics,
                        projection_classification=classification,
                    )

                    # Record checkpoint in store to advance status
                    from .pending_store import OutcomeCheckpoint
                    self._store.record_checkpoint(
                        client_id=pending.client_id,
                        prediction_id=pending.prediction_id,
                        checkpoint=OutcomeCheckpoint(
                            checkpoint_type=checkpoint_type,
                            platform_metrics=metrics,
                            composite_signal=metrics["primary_signal"],
                        ),
                    )

                    if checkpoint_type == "7d":
                        self._store.close(
                            client_id=pending.client_id,
                            prediction_id=pending.prediction_id,
                            composite_score=metrics["primary_signal"],
                            projection_classification=classification,
                        )

                    results["processed"] += 1
                    results["details"].append({
                        "prediction_id": pending.prediction_id,
                        "action": "processed",
                        "checkpoint": checkpoint_type,
                        "classification": classification,
                        "signal": metrics["primary_signal"],
                    })

                except Exception as e:
                    logger.error(
                        f"Checkpoint failed for {pending.prediction_id}: {e}"
                    )
                    results["failed"] += 1
                    results["details"].append({
                        "prediction_id": pending.prediction_id,
                        "action": "failed",
                        "error": str(e),
                    })

        # Expire stale outcomes that were never resolved
        expired = self._store.expire_stale(max_age_days=14)
        results["expired"] = expired

        logger.info(
            f"Checkpoint processing complete: "
            f"processed={results['processed']}, "
            f"failed={results['failed']}, "
            f"skipped={results['skipped']}, "
            f"expired={expired}"
        )
        return results

    def _collect_metrics(
        self, pending: PendingOutcome
    ) -> Optional[Dict[str, Any]]:
        """Collect platform metrics using delivery_metadata."""
        delivery = pending.delivery_metadata or {}
        metrics: Dict[str, Any] = {}

        # Route 1: MH1HQ MCP — query skill run results
        if delivery.get("skill_run_id") or delivery.get("module_id"):
            try:
                run_data = self._query_mh1hq(delivery)
                if run_data:
                    metrics.update(run_data)
            except Exception as e:
                logger.debug(f"MH1HQ query failed: {e}")

        # Route 2: Direct platform metrics via campaign/ad IDs
        if delivery.get("campaign_id") or delivery.get("ad_set_id"):
            try:
                platform_data = self._query_platform(delivery)
                if platform_data:
                    metrics.update(platform_data)
            except Exception as e:
                logger.debug(f"Platform query failed: {e}")

        # Route 3: Report URL — check if report was viewed/actioned
        if delivery.get("report_url"):
            try:
                report_data = self._check_report(delivery)
                if report_data:
                    metrics.update(report_data)
            except Exception as e:
                logger.debug(f"Report check failed: {e}")

        # Compute primary signal from collected metrics
        if metrics:
            channel_config = None
            if pending.channel_id:
                try:
                    from lib.intelligence.adapters.channels import (
                        get_channel_config,
                    )
                    channel_config = get_channel_config(pending.channel_id)
                except ImportError:
                    pass

            try:
                from lib.intelligence.outcomes.signal_computer import (
                    CompositeSignalComputer,
                )
                computer = CompositeSignalComputer()

                expected_score = pending.prediction.get("expected_signal", 0.5)
                expected_baseline = pending.prediction.get("expected_baseline", 1.0)
                if expected_baseline > 0:
                    expected_ratio = expected_score / expected_baseline
                else:
                    expected_ratio = expected_score

                composite = computer.compute(
                    skill_name=pending.skill_name,
                    expected_score=expected_ratio,
                    platform_metrics=metrics,
                    channel_config=channel_config,
                )
                metrics["primary_signal"] = composite.composite_score
                metrics["projection_classification"] = composite.projection_classification
            except Exception as e:
                logger.debug(f"Composite signal computation failed: {e}")
                # Fallback: use first numeric metric as primary signal
                for v in metrics.values():
                    if isinstance(v, (int, float)):
                        metrics["primary_signal"] = float(v)
                        break

        return metrics if metrics.get("primary_signal") is not None else None

    def _classify(self, pending: PendingOutcome, observed_signal: float) -> str:
        """Classify outcome vs prediction."""
        expected = pending.prediction.get("expected_signal", 0.5)
        if expected == 0:
            return "accurate_projection"
        ratio = observed_signal / expected if expected != 0 else 1.0
        if ratio < 0.8:
            return "under_projection"
        elif ratio > 1.2:
            return "over_projection"
        return "accurate_projection"

    def _query_mh1hq(self, delivery: Dict[str, Any]) -> Optional[Dict]:
        """Query MH1HQ for execution results via MCP."""
        # Stub — implement when MCP client is available in BrightMatter
        return None

    def _query_platform(self, delivery: Dict[str, Any]) -> Optional[Dict]:
        """Query platform APIs for campaign performance."""
        # Stub — implement per platform (Meta, Google, etc.)
        return None

    def _check_report(self, delivery: Dict[str, Any]) -> Optional[Dict]:
        """Check if a delivered report was viewed/actioned."""
        # Stub — check Firebase user_activity or PostHog
        return None


__all__ = ["CheckpointProcessor"]
