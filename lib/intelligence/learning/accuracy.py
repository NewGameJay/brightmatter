"""
MH1 Prediction Accuracy Scorer

Retrospective evaluation of prediction quality from the BrightMatter design.
Runs daily to compute MAE, confidence calibration, trend accuracy, and
exploration hit rate from recent episodic memories.

Firebase path:
  system/intelligence/accuracy_reports/{YYYY-MM-DD}
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccuracyReport:
    """Structured output from a prediction accuracy evaluation."""
    date: str
    lookback_days: int
    total_episodes: int = 0
    mean_absolute_error: float = 0.0
    per_skill_error: Dict[str, float] = field(default_factory=dict)
    confidence_calibration: Dict[str, float] = field(default_factory=dict)
    trend_accuracy: float = 0.0
    exploration_hit_rate: float = 0.0
    accuracy_trend: str = "stable"  # improving | stable | declining

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "lookback_days": self.lookback_days,
            "total_episodes": self.total_episodes,
            "mean_absolute_error": self.mean_absolute_error,
            "per_skill_error": self.per_skill_error,
            "confidence_calibration": self.confidence_calibration,
            "trend_accuracy": self.trend_accuracy,
            "exploration_hit_rate": self.exploration_hit_rate,
            "accuracy_trend": self.accuracy_trend,
        }


class AccuracyScorer:
    """Retrospective evaluation of prediction quality."""

    _REPORT_COLLECTION = "system/intelligence/accuracy_reports"

    def __init__(self, episodic_store: Any, firebase_client: Any = None):
        self._episodic = episodic_store
        self._firebase = firebase_client

    def score_recent_predictions(
        self, lookback_days: int = 7
    ) -> AccuracyReport:
        """Pull recent episodic memories and score prediction accuracy."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report = AccuracyReport(date=today, lookback_days=lookback_days)

        episodes = self._collect_recent_episodes(lookback_days)
        if not episodes:
            logger.info("No recent episodes for accuracy scoring")
            return report

        report.total_episodes = len(episodes)
        report.mean_absolute_error = self._compute_mae(episodes)
        report.per_skill_error = self._compute_per_skill_error(episodes)
        report.confidence_calibration = self._compute_calibration(episodes)
        report.trend_accuracy = self._compute_trend_accuracy(episodes)
        report.exploration_hit_rate = self._compute_exploration_value(episodes)
        report.accuracy_trend = self._determine_trend()

        self._persist_report(report)

        logger.info(
            f"Accuracy report: MAE={report.mean_absolute_error:.3f}, "
            f"trend_acc={report.trend_accuracy:.2f}, "
            f"episodes={report.total_episodes}"
        )
        return report

    def _collect_recent_episodes(self, lookback_days: int) -> List[Dict[str, Any]]:
        """Gather recent episodic memories across all tenants."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).isoformat()

        episodes: List[Dict[str, Any]] = []

        if not hasattr(self._episodic, "_list_tenants"):
            return episodes

        for tenant_id in self._episodic._list_tenants():
            for skill in self._episodic._list_skills_for_tenant(tenant_id):
                try:
                    raw = self._episodic._firebase.get_collection(
                        collection=self._episodic._get_collection_path(tenant_id, skill)
                    )
                    if not raw:
                        continue
                    for doc in raw:
                        created = doc.get("created_at", "")
                        if created >= cutoff:
                            doc["_tenant_id"] = tenant_id
                            doc["_skill_name"] = skill
                            episodes.append(doc)
                except Exception:
                    pass

        return episodes

    def _compute_mae(self, episodes: List[Dict[str, Any]]) -> float:
        errors = []
        for ep in episodes:
            outcome = ep.get("outcome", {})
            pe = outcome.get("prediction_error")
            if pe is not None:
                errors.append(abs(pe))
        return sum(errors) / len(errors) if errors else 0.0

    def _compute_per_skill_error(
        self, episodes: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        skill_errors: Dict[str, List[float]] = {}
        for ep in episodes:
            skill = ep.get("_skill_name", ep.get("prediction", {}).get("skill_name", "unknown"))
            pe = ep.get("outcome", {}).get("prediction_error")
            if pe is not None:
                skill_errors.setdefault(skill, []).append(abs(pe))
        return {
            skill: sum(errs) / len(errs)
            for skill, errs in skill_errors.items()
            if errs
        }

    def _compute_calibration(
        self, episodes: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Bin predictions by confidence decile, check observed success rate matches."""
        bins: Dict[str, List[bool]] = {}
        for ep in episodes:
            pred = ep.get("prediction", {})
            confidence = pred.get("confidence", 0.5)
            outcome = ep.get("outcome", {})
            success = outcome.get("goal_completed", False)

            decile = str(round(confidence, 1))
            bins.setdefault(decile, []).append(success)

        calibration: Dict[str, float] = {}
        for decile, outcomes in bins.items():
            if outcomes:
                calibration[decile] = sum(outcomes) / len(outcomes)
        return calibration

    def _compute_trend_accuracy(self, episodes: List[Dict[str, Any]]) -> float:
        """When we predicted improvement, did it improve?"""
        correct = 0
        total = 0
        for ep in episodes:
            pred = ep.get("prediction", {})
            outcome = ep.get("outcome", {})

            expected_signal = pred.get("expected_signal", 0)
            expected_baseline = pred.get("expected_baseline", 1)
            observed_signal = outcome.get("observed_signal", 0)
            observed_baseline = outcome.get("observed_baseline", 1)

            if expected_baseline == 0 or observed_baseline == 0:
                continue

            expected_ratio = expected_signal / expected_baseline
            observed_ratio = observed_signal / observed_baseline

            predicted_up = expected_ratio > 1.0
            actually_up = observed_ratio > 1.0

            total += 1
            if predicted_up == actually_up:
                correct += 1

        return correct / total if total > 0 else 0.0

    def _compute_exploration_value(self, episodes: List[Dict[str, Any]]) -> float:
        """What % of exploration runs discovered better parameters?"""
        explore_total = 0
        explore_hits = 0
        for ep in episodes:
            pred = ep.get("prediction", {})
            if not pred.get("is_exploration"):
                continue
            explore_total += 1
            outcome = ep.get("outcome", {})
            if outcome.get("goal_completed"):
                explore_hits += 1

        return explore_hits / explore_total if explore_total > 0 else 0.0

    def _determine_trend(self) -> str:
        """Compare current MAE against last 3 reports to determine trend."""
        if not self._firebase or not hasattr(self._firebase, "get_collection"):
            return "stable"
        try:
            docs = self._firebase.get_collection(
                collection=self._REPORT_COLLECTION,
                order_by="date",
                order_direction="DESCENDING",
                limit=4,
            )
            if not docs or len(docs) < 2:
                return "stable"

            recent_mae = [d.get("mean_absolute_error", 0) for d in docs[:3]]
            if len(recent_mae) < 2:
                return "stable"

            if recent_mae[0] < recent_mae[-1] * 0.95:
                return "improving"
            if recent_mae[0] > recent_mae[-1] * 1.05:
                return "declining"
            return "stable"
        except Exception:
            return "stable"

    def _persist_report(self, report: AccuracyReport):
        if not self._firebase or not hasattr(self._firebase, "set_document"):
            return
        try:
            self._firebase.set_document(
                self._REPORT_COLLECTION, report.date, report.to_dict(), merge=True,
            )
        except Exception as e:
            logger.debug(f"Failed to persist accuracy report: {e}")


__all__ = ["AccuracyReport", "AccuracyScorer"]
