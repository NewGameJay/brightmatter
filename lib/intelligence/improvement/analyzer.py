"""
MH1 Improvement Analyzer

Scans closed outcomes from the pending outcome store for systematic
patterns that indicate a skill, agent, or template needs improvement.

A pattern is "systematic" when a skill has 3+ consecutive under-projections
for similar client profiles, or when client feedback is consistently negative,
or when edit depth is consistently high (content doesn't match client voice).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_CONSECUTIVE_UNDER = 3
MIN_FEEDBACK_SAMPLES = 3
HIGH_EDIT_DEPTH = 0.5


@dataclass
class ImprovementCandidate:
    """A skill/domain combination that shows systematic under-performance."""
    candidate_id: str = ""
    skill_name: str = ""
    domain: str = ""
    client_segment: str = ""  # e.g., "enterprise_saas", "dtc_ecommerce"
    pattern_type: str = ""  # "under_projection" | "negative_feedback" | "heavy_editing"
    pattern_description: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    severity: float = 0.0  # frequency x magnitude of under-projection
    consecutive_count: int = 0
    avg_delta: float = 0.0
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "skill_name": self.skill_name,
            "domain": self.domain,
            "client_segment": self.client_segment,
            "pattern_type": self.pattern_type,
            "pattern_description": self.pattern_description,
            "evidence": self.evidence,
            "severity": self.severity,
            "consecutive_count": self.consecutive_count,
            "avg_delta": self.avg_delta,
            "created_at": self.created_at,
        }


class ImprovementAnalyzer:
    """
    Scans closed outcomes for systematic improvement opportunities.

    Groups outcomes by (skill_name, domain) and looks for:
    1. Consecutive under-projections (3+)
    2. Consistently negative client feedback
    3. Consistently high edit depth (content misfit)
    """

    def __init__(
        self,
        firebase_client: Any = None,
        min_consecutive: int = MIN_CONSECUTIVE_UNDER,
        lookback_days: int = 30,
    ):
        self._firebase = firebase_client
        self._min_consecutive = min_consecutive
        self._lookback_days = lookback_days

    def analyze(
        self, closed_outcomes: Optional[List[Any]] = None
    ) -> List[ImprovementCandidate]:
        """
        Analyze closed outcomes for systematic patterns.

        Args:
            closed_outcomes: Pre-loaded list of PendingOutcome objects.
                If None, loads from Firebase via PendingOutcomeStore.
        """
        if closed_outcomes is None:
            closed_outcomes = self._load_closed_outcomes()

        if not closed_outcomes:
            return []

        candidates: List[ImprovementCandidate] = []

        # Group by (skill_name, domain)
        groups: Dict[str, List[Any]] = defaultdict(list)
        for outcome in closed_outcomes:
            key = f"{outcome.skill_name}|{outcome.prediction.get('domain', 'generic')}"
            groups[key].append(outcome)

        now = datetime.now(timezone.utc).isoformat()

        for group_key, outcomes in groups.items():
            skill_name, domain = group_key.split("|", 1)

            # Sort by created_at for consecutive analysis
            outcomes.sort(key=lambda o: o.created_at or "")

            # Check for consecutive under-projections
            consecutive_under = 0
            deltas: List[float] = []
            evidence: List[Dict[str, Any]] = []

            for outcome in outcomes:
                if outcome.projection_classification == "under_projection":
                    consecutive_under += 1
                    delta = outcome.composite_score or 0.0
                    expected = outcome.prediction.get("expected_signal", 0.5)
                    deltas.append(expected - delta)
                    evidence.append({
                        "prediction_id": outcome.prediction_id,
                        "client_id": outcome.client_id,
                        "composite_score": outcome.composite_score,
                        "classification": outcome.projection_classification,
                        "closed_at": outcome.closed_at,
                    })
                else:
                    consecutive_under = 0
                    deltas.clear()
                    evidence.clear()

            if consecutive_under >= self._min_consecutive:
                avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
                severity = consecutive_under * abs(avg_delta)
                candidates.append(ImprovementCandidate(
                    candidate_id=f"imp_{skill_name}_{now[:10]}",
                    skill_name=skill_name,
                    domain=domain,
                    pattern_type="under_projection",
                    pattern_description=(
                        f"{skill_name} has {consecutive_under} consecutive "
                        f"under-projections (avg delta={avg_delta:.3f})"
                    ),
                    evidence=evidence[-10:],
                    severity=severity,
                    consecutive_count=consecutive_under,
                    avg_delta=avg_delta,
                    created_at=now,
                ))

            # Check for consistently negative feedback
            feedback_scores = []
            for outcome in outcomes:
                for cp in (outcome.checkpoints or []):
                    rating = (cp.feedback_signals or {}).get("rating")
                    if rating is not None:
                        try:
                            feedback_scores.append(float(rating))
                        except (TypeError, ValueError):
                            pass

            if len(feedback_scores) >= MIN_FEEDBACK_SAMPLES:
                avg_rating = sum(feedback_scores) / len(feedback_scores)
                if avg_rating < 2.5:  # below neutral on 5-point scale
                    candidates.append(ImprovementCandidate(
                        candidate_id=f"imp_fb_{skill_name}_{now[:10]}",
                        skill_name=skill_name,
                        domain=domain,
                        pattern_type="negative_feedback",
                        pattern_description=(
                            f"{skill_name} has avg feedback rating {avg_rating:.1f}/5 "
                            f"over {len(feedback_scores)} samples"
                        ),
                        evidence=[{"avg_rating": avg_rating, "n_samples": len(feedback_scores)}],
                        severity=(2.5 - avg_rating) * len(feedback_scores),
                        avg_delta=2.5 - avg_rating,
                        created_at=now,
                    ))

            # Check for consistently high edit depth
            edit_depths = []
            for outcome in outcomes:
                for cp in (outcome.checkpoints or []):
                    ed = (cp.behavior_signals or {}).get("edit_depth")
                    if ed is not None:
                        try:
                            edit_depths.append(float(ed))
                        except (TypeError, ValueError):
                            pass

            if len(edit_depths) >= MIN_FEEDBACK_SAMPLES:
                avg_edit = sum(edit_depths) / len(edit_depths)
                if avg_edit > HIGH_EDIT_DEPTH:
                    candidates.append(ImprovementCandidate(
                        candidate_id=f"imp_ed_{skill_name}_{now[:10]}",
                        skill_name=skill_name,
                        domain=domain,
                        pattern_type="heavy_editing",
                        pattern_description=(
                            f"{skill_name} outputs are heavily edited: "
                            f"avg edit depth {avg_edit:.0%} over {len(edit_depths)} samples"
                        ),
                        evidence=[{"avg_edit_depth": avg_edit, "n_samples": len(edit_depths)}],
                        severity=avg_edit * len(edit_depths),
                        avg_delta=avg_edit,
                        created_at=now,
                    ))

        # Also analyze over-projections for insight extraction
        for group_key, outcomes in groups.items():
            skill_name, domain = group_key.split("|", 1)
            over_count = sum(
                1 for o in outcomes
                if o.projection_classification == "over_projection"
            )
            if over_count >= self._min_consecutive:
                logger.info(
                    f"[improvement] {skill_name} has {over_count} over-projections — "
                    f"capturing as positive insight for procedural memory"
                )

        candidates.sort(key=lambda c: c.severity, reverse=True)
        return candidates

    def _load_closed_outcomes(self) -> List[Any]:
        """Load closed outcomes from the pending store."""
        if not self._firebase:
            return []
        try:
            from lib.intelligence.outcomes.pending_store import PendingOutcomeStore
            store = PendingOutcomeStore(self._firebase)
            return store.list_closed(since_days=self._lookback_days)
        except Exception as e:
            logger.error(f"Failed to load closed outcomes: {e}")
            return []


__all__ = ["ImprovementAnalyzer", "ImprovementCandidate"]
