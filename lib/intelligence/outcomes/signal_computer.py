"""
MH1 Composite Signal Computer

Translates three signal sources into a single composite score and
projection classification for the deferred outcome learning loop.

Signal sources and default weights:
    Platform metrics   (40%) — email open/click rates, pipeline velocity, campaign performance
    Client feedback    (35%) — portal ratings, structured feedback, comment sentiment
    User behavior      (25%) — time-to-approval, edit depth, report engagement, sharing

Projection classification:
    under_projection   — composite < expected - threshold
    over_projection    — composite > expected + threshold
    accurate_projection — within threshold band
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECTION_THRESHOLD = 0.15


@dataclass
class CompositeSignal:
    """Result of composite signal computation."""
    platform_score: float = 0.0
    feedback_score: float = 0.0
    behavior_score: float = 0.0
    composite_score: float = 0.0
    projection_classification: str = "accurate_projection"
    expected_score: float = 0.5
    delta: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform_score": self.platform_score,
            "feedback_score": self.feedback_score,
            "behavior_score": self.behavior_score,
            "composite_score": self.composite_score,
            "projection_classification": self.projection_classification,
            "expected_score": self.expected_score,
            "delta": self.delta,
            "details": self.details,
        }


# Per-skill metric extractors. Each maps raw platform metrics to a 0-1 score.
_SKILL_METRIC_EXTRACTORS = {
    "lifecycle-audit": ["churn_rate_delta", "retention_improvement"],
    "churn-prediction": ["churn_rate_delta", "retention_improvement"],
    "at-risk-detection": ["churn_rate_delta", "at_risk_save_rate"],
    "dormant-detection": ["reactivation_rate"],
    "reactivation-detection": ["reactivation_rate"],
    "email-copy-generator": ["open_rate", "click_rate", "conversion_rate"],
    "cohort-email-builder": ["open_rate", "click_rate", "conversion_rate"],
    "pipeline-analysis": ["pipeline_velocity_change", "win_rate_delta"],
    "deal-velocity": ["pipeline_velocity_change", "win_rate_delta"],
    "conversion-funnel": ["conversion_rate", "funnel_improvement"],
    "upsell-candidates": ["upsell_conversion_rate", "revenue_uplift"],
    "renewal-tracker": ["renewal_rate", "churn_rate_delta"],
    "positioning-angles": ["engagement_rate", "conversion_uplift"],
    "direct-response-copy": ["engagement_rate", "conversion_uplift"],
    "seo-content": ["organic_traffic_change", "ranking_improvement"],
    "social-listening-collect": ["engagement_velocity", "reach_growth"],
}


class CompositeSignalComputer:
    """
    Computes a weighted composite score from platform metrics, client
    feedback, and user behavior, then classifies the projection accuracy.
    """

    def __init__(
        self,
        platform_weight: float = 0.40,
        feedback_weight: float = 0.35,
        behavior_weight: float = 0.25,
        threshold: float = PROJECTION_THRESHOLD,
    ):
        self.platform_weight = platform_weight
        self.feedback_weight = feedback_weight
        self.behavior_weight = behavior_weight
        self.threshold = threshold

    def compute(
        self,
        skill_name: str,
        expected_score: float,
        platform_metrics: Optional[Dict[str, Any]] = None,
        feedback_signals: Optional[Dict[str, Any]] = None,
        behavior_signals: Optional[Dict[str, Any]] = None,
        baseline_metrics: Optional[Dict[str, Any]] = None,
        channel_config: Optional[Any] = None,
    ) -> CompositeSignal:
        """
        Compute composite signal and classify projection accuracy.

        Args:
            skill_name: Skill that produced the deliverable.
            expected_score: The prediction's expected signal
                (Prediction.expected_signal / expected_baseline ratio).
            platform_metrics: Raw platform metrics for the checkpoint window.
            feedback_signals: Client feedback data (rating, sentiment, etc).
            behavior_signals: User behavior data (edit_depth, time_to_approval, etc).
            baseline_metrics: Phase 0 snapshot for delta computation.
            channel_config: Optional ChannelConfig with primary_signal and
                secondary_signals to use for platform scoring.
        """
        platform = self._score_platform(
            skill_name, platform_metrics or {}, baseline_metrics or {},
            channel_config=channel_config,
        )
        feedback = self._score_feedback(feedback_signals or {})
        behavior = self._score_behavior(behavior_signals or {})

        composite = (
            platform * self.platform_weight
            + feedback * self.feedback_weight
            + behavior * self.behavior_weight
        )

        delta = composite - expected_score
        if delta < -self.threshold:
            classification = "under_projection"
        elif delta > self.threshold:
            classification = "over_projection"
        else:
            classification = "accurate_projection"

        result = CompositeSignal(
            platform_score=platform,
            feedback_score=feedback,
            behavior_score=behavior,
            composite_score=composite,
            projection_classification=classification,
            expected_score=expected_score,
            delta=delta,
            details={
                "platform_metrics_used": list((platform_metrics or {}).keys()),
                "has_feedback": bool(feedback_signals),
                "has_behavior": bool(behavior_signals),
                "weights": {
                    "platform": self.platform_weight,
                    "feedback": self.feedback_weight,
                    "behavior": self.behavior_weight,
                },
            },
        )

        logger.info(
            f"Composite signal for {skill_name}: {composite:.3f} "
            f"(expected={expected_score:.3f}, delta={delta:+.3f}, "
            f"class={classification})"
        )
        return result

    def _score_platform(
        self,
        skill_name: str,
        metrics: Dict[str, Any],
        baseline: Dict[str, Any],
        channel_config: Optional[Any] = None,
    ) -> float:
        """
        Score platform metrics against baseline. Returns 0-1.

        When a ``channel_config`` is provided its ``primary_signal`` and
        ``secondary_signals`` are used instead of the hard-coded per-skill
        extractor table.
        """
        if not metrics:
            return 0.5

        relevant_keys = None
        if channel_config is not None:
            primary = getattr(channel_config, "primary_signal", None)
            secondary = getattr(channel_config, "secondary_signals", [])
            if primary:
                relevant_keys = [primary] + list(secondary)

        if not relevant_keys:
            relevant_keys = _SKILL_METRIC_EXTRACTORS.get(skill_name, [])
        if not relevant_keys:
            return _generic_platform_score(metrics, baseline)

        scores: List[float] = []
        for key in relevant_keys:
            current = metrics.get(key)
            if current is None:
                continue
            try:
                current_val = float(current)
            except (TypeError, ValueError):
                continue

            base_val = float(baseline.get(key, 0.0) or 0.0)
            if base_val == 0.0:
                scores.append(min(1.0, max(0.0, current_val)))
            else:
                delta_ratio = (current_val - base_val) / abs(base_val)
                scores.append(_sigmoid_normalize(delta_ratio))

        return sum(scores) / len(scores) if scores else 0.5

    def _score_feedback(self, signals: Dict[str, Any]) -> float:
        """
        Score client feedback signals. Returns 0-1.

        Inputs:
            rating: 1-5 star rating -> linearly mapped to 0-1
            sentiment: -1 to +1 sentiment -> mapped to 0-1
            comment_count: number of comments (engagement signal)
        """
        if not signals:
            return 0.5

        scores: List[float] = []

        rating = signals.get("rating")
        if rating is not None:
            try:
                scores.append((float(rating) - 1.0) / 4.0)
            except (TypeError, ValueError):
                pass

        sentiment = signals.get("sentiment")
        if sentiment is not None:
            try:
                scores.append((float(sentiment) + 1.0) / 2.0)
            except (TypeError, ValueError):
                pass

        has_positive = signals.get("has_positive_comment", False)
        if has_positive:
            scores.append(0.8)

        has_negative = signals.get("has_negative_comment", False)
        if has_negative:
            scores.append(0.2)

        return sum(scores) / len(scores) if scores else 0.5

    def _score_behavior(self, signals: Dict[str, Any]) -> float:
        """
        Score user behavior signals. Returns 0-1.

        Higher scores = positive engagement. Heavy editing = negative.
        """
        if not signals:
            return 0.5

        scores: List[float] = []

        # time_to_approval: fast = good (hours), slow = bad (days)
        tta = signals.get("time_to_approval_hours")
        if tta is not None:
            try:
                hours = float(tta)
                if hours <= 4:
                    scores.append(1.0)
                elif hours <= 24:
                    scores.append(0.7)
                elif hours <= 72:
                    scores.append(0.4)
                else:
                    scores.append(0.2)
            except (TypeError, ValueError):
                pass

        # edit_depth: heavy editing = content missed the mark (inversely correlated)
        edit_depth = signals.get("edit_depth")
        if edit_depth is not None:
            try:
                depth = float(edit_depth)
                scores.append(max(0.0, 1.0 - depth))
            except (TypeError, ValueError):
                pass

        # report_views: more views = higher engagement
        views = signals.get("report_views")
        if views is not None:
            try:
                v = int(views)
                scores.append(min(1.0, v / 10.0))
            except (TypeError, ValueError):
                pass

        # scroll_depth: deeper = more engaged
        scroll = signals.get("scroll_depth_pct")
        if scroll is not None:
            try:
                scores.append(min(1.0, float(scroll) / 100.0))
            except (TypeError, ValueError):
                pass

        # sharing: externally shared = strong positive
        shared = signals.get("shared")
        if shared:
            scores.append(1.0)

        # adoption: did they implement recommendations?
        adopted = signals.get("adopted")
        if adopted is not None:
            scores.append(1.0 if adopted else 0.2)

        return sum(scores) / len(scores) if scores else 0.5


def _sigmoid_normalize(delta_ratio: float, steepness: float = 3.0) -> float:
    """Map a delta ratio to 0-1 using a sigmoid curve centered at 0."""
    import math
    return 1.0 / (1.0 + math.exp(-steepness * delta_ratio))


def _generic_platform_score(
    metrics: Dict[str, Any], baseline: Dict[str, Any]
) -> float:
    """Fallback scoring for skills without specific metric extractors."""
    numeric_keys = [
        k for k, v in metrics.items()
        if isinstance(v, (int, float)) and not k.startswith("_")
    ]
    if not numeric_keys:
        return 0.5

    scores: List[float] = []
    for key in numeric_keys[:10]:
        current = float(metrics[key])
        base = float(baseline.get(key, 0.0) or 0.0)
        if base == 0.0:
            scores.append(min(1.0, max(0.0, current)))
        else:
            delta = (current - base) / abs(base)
            scores.append(_sigmoid_normalize(delta))

    return sum(scores) / len(scores) if scores else 0.5


__all__ = ["CompositeSignalComputer", "CompositeSignal", "PROJECTION_THRESHOLD"]
