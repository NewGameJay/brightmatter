"""
MH1 Shadow/Ghost Template Testing

Implements the BrightMatter design for parallel candidate evaluation:
- Spawn shadow candidates when prediction error exceeds threshold
- Dual-score every outcome against both production and candidate weights
- Promote candidates that demonstrate sustained improvement
- Archive production weights for rollback

Firebase paths:
  system/intelligence/shadow_state      – active candidate + production snapshot
  system/intelligence/shadow_history    – archived promotion/rejection records
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ShadowConfig:
    error_threshold: float = 0.15
    min_observations: int = 20
    min_improvement: float = 0.03
    test_duration_days: int = 14
    evaluation_interval: int = 10
    perturbation_range: float = 0.10
    base_learning_rate: float = 0.1


@dataclass
class ShadowCandidate:
    version: str
    weights: Dict[str, float]
    created_at: str
    status: str  # testing | promoted | rejected
    test_outcomes: List[Dict[str, float]] = field(default_factory=list)
    production_error_at_spawn: float = 0.0
    channel_timing: Dict[str, Dict[str, float]] = field(default_factory=dict)
    hypothesis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "weights": self.weights,
            "created_at": self.created_at,
            "status": self.status,
            "test_outcomes": self.test_outcomes[-200:],
            "production_error_at_spawn": self.production_error_at_spawn,
            "channel_timing": self.channel_timing,
            "hypothesis": self.hypothesis,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ShadowCandidate:
        return cls(
            version=d.get("version", ""),
            weights=d.get("weights", {}),
            created_at=d.get("created_at", ""),
            status=d.get("status", "testing"),
            test_outcomes=d.get("test_outcomes", []),
            production_error_at_spawn=d.get("production_error_at_spawn", 0.0),
            channel_timing=d.get("channel_timing", {}),
            hypothesis=d.get("hypothesis", ""),
        )


class ShadowManager:
    """Manages shadow/ghost template testing for the intelligence system."""

    _STATE_COLLECTION = "system/intelligence/shadow_state"
    _HISTORY_COLLECTION = "system/intelligence/shadow_history"

    def __init__(
        self,
        firebase_client: Any,
        semantic_store: Any,
        config: Optional[ShadowConfig] = None,
    ):
        self._firebase = firebase_client
        self._semantic = semantic_store
        self._config = config or ShadowConfig()
        self._candidate: Optional[ShadowCandidate] = None
        self._production_weights: Dict[str, float] = {}
        self._outcome_count = 0
        self._load_state()

    @property
    def active_candidate(self) -> Optional[ShadowCandidate]:
        return self._candidate

    def _load_state(self):
        """Load shadow state from Firebase."""
        if not self._firebase or not hasattr(self._firebase, "get_document"):
            return
        try:
            doc = self._firebase.get_document(
                self._STATE_COLLECTION, "current"
            )
            if not doc:
                return
            self._production_weights = doc.get("production_weights", {})
            self._outcome_count = doc.get("outcome_count", 0)
            cand_data = doc.get("candidate")
            if cand_data and cand_data.get("status") == "testing":
                self._candidate = ShadowCandidate.from_dict(cand_data)
        except Exception as e:
            logger.debug(f"Could not load shadow state: {e}")

    def _persist_state(self):
        """Persist shadow state to Firebase."""
        if not self._firebase or not hasattr(self._firebase, "set_document"):
            return
        try:
            data: Dict[str, Any] = {
                "production_weights": self._production_weights,
                "outcome_count": self._outcome_count,
            }
            if self._candidate:
                data["candidate"] = self._candidate.to_dict()
            else:
                data["candidate"] = None
            self._firebase.set_document(
                self._STATE_COLLECTION, "current", data, merge=True,
            )
        except Exception as e:
            logger.debug(f"Failed to persist shadow state: {e}")

    def dual_score(
        self, prediction_error: float, production_error: float
    ) -> Dict[str, Any]:
        """Record a dual-scored outcome against both production and candidate."""
        self._outcome_count += 1
        result: Dict[str, Any] = {"has_candidate": self._candidate is not None}

        if self._candidate and self._candidate.status == "testing":
            self._candidate.test_outcomes.append({
                "prediction_error": prediction_error,
                "production_error": production_error,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            result["candidate_version"] = self._candidate.version

        if self._outcome_count % self._config.evaluation_interval == 0:
            self._persist_state()

        return result

    def maybe_spawn_candidate(
        self, recent_errors: List[float]
    ) -> Optional[ShadowCandidate]:
        """Spawn a shadow candidate if average recent error exceeds threshold."""
        if self._candidate and self._candidate.status == "testing":
            return None

        if len(recent_errors) < self._config.evaluation_interval:
            return None

        avg_error = sum(abs(e) for e in recent_errors) / len(recent_errors)
        if avg_error <= self._config.error_threshold:
            return None

        # Two-path candidate generation:
        # Path 1: Hypothesis from improvement analysis (targeted)
        # Path 2: Random perturbation (fallback)
        candidate = self._generate_hypothesis_candidate()
        if candidate is None:
            weights = self._generate_candidate_weights()
            if not weights:
                return None
            channel_timing = self._generate_channel_timing()
            candidate = ShadowCandidate(
                version=f"shadow-{uuid.uuid4().hex[:8]}",
                weights=weights,
                channel_timing=channel_timing,
                created_at=datetime.now(timezone.utc).isoformat(),
                status="testing",
                production_error_at_spawn=avg_error,
            )
        else:
            candidate.production_error_at_spawn = avg_error

        self._candidate = candidate
        self._persist_state()
        logger.info(
            f"Spawned shadow candidate {self._candidate.version} "
            f"(production error {avg_error:.3f} > {self._config.error_threshold})"
        )
        return self._candidate

    def evaluate_candidate(self) -> Dict[str, Any]:
        """Evaluate the current candidate for promotion or rejection."""
        result: Dict[str, Any] = {
            "action": "none",
            "candidate_version": None,
            "improvement": 0.0,
        }

        if not self._candidate or self._candidate.status != "testing":
            return result

        result["candidate_version"] = self._candidate.version
        outcomes = self._candidate.test_outcomes

        if len(outcomes) < self._config.min_observations:
            result["action"] = "insufficient_data"
            result["observations"] = len(outcomes)
            result["required"] = self._config.min_observations
            return result

        created = datetime.fromisoformat(
            self._candidate.created_at.replace("Z", "+00:00")
        )
        age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
        if age_days < self._config.test_duration_days:
            result["action"] = "testing"
            result["days_remaining"] = self._config.test_duration_days - age_days
            return result

        prod_errors = [abs(o["production_error"]) for o in outcomes]
        cand_errors = [abs(o["prediction_error"]) for o in outcomes]
        prod_mean = sum(prod_errors) / len(prod_errors) if prod_errors else 1.0
        cand_mean = sum(cand_errors) / len(cand_errors) if cand_errors else 1.0

        improvement = prod_mean - cand_mean

        if improvement >= self._config.min_improvement:
            result["action"] = "promoted"
            result["improvement"] = improvement
            self._promote_candidate(improvement)
        else:
            result["action"] = "rejected"
            result["improvement"] = improvement
            self._reject_candidate(improvement)

        return result

    def _promote_candidate(self, improvement: float):
        """Archive production weights, promote candidate, update channel timing."""
        if not self._candidate:
            return

        history_entry = {
            "version": self._candidate.version,
            "action": "promoted",
            "improvement": improvement,
            "observations": len(self._candidate.test_outcomes),
            "previous_weights": self._production_weights,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "production_error_at_spawn": self._candidate.production_error_at_spawn,
            "channel_timing": self._candidate.channel_timing,
            "hypothesis": self._candidate.hypothesis,
        }
        self._archive_history(history_entry)

        self._production_weights = dict(self._candidate.weights)
        self._apply_weights_to_patterns(self._candidate.weights)

        if self._candidate.channel_timing:
            self._apply_channel_timing(self._candidate.channel_timing)

        logger.info(
            f"Promoted shadow {self._candidate.version} "
            f"(+{improvement:.3f} improvement, "
            f"hypothesis='{self._candidate.hypothesis}')"
        )

        self._candidate = None
        self._persist_state()

    def _reject_candidate(self, improvement: float):
        """Reject the current candidate."""
        if not self._candidate:
            return

        history_entry = {
            "version": self._candidate.version,
            "action": "rejected",
            "improvement": improvement,
            "observations": len(self._candidate.test_outcomes),
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "channel_timing": self._candidate.channel_timing,
            "hypothesis": self._candidate.hypothesis,
        }
        self._archive_history(history_entry)

        logger.info(
            f"Rejected shadow {self._candidate.version} "
            f"(improvement {improvement:.3f} < {self._config.min_improvement}, "
            f"hypothesis='{self._candidate.hypothesis}')"
        )

        self._candidate = None
        self._persist_state()

    def _generate_hypothesis_candidate(self) -> Optional[ShadowCandidate]:
        """Generate a candidate from improvement analysis (targeted path).

        Uses ImprovementAnalyzer to find systematic failures, then
        ImprovementProposer to generate a hypothesis. The hypothesis
        drives targeted weight perturbations instead of random noise.
        """
        try:
            from ..improvement.analyzer import ImprovementAnalyzer
            from ..improvement.proposer import ImprovementProposer

            analyzer = ImprovementAnalyzer(firebase_client=self._firebase)
            candidates = analyzer.analyze()
            if not candidates:
                return None

            proposer = ImprovementProposer()
            proposals = proposer.propose(candidates[:3])
            if not proposals:
                return None

            best_proposal = proposals[0]
            hypothesis = best_proposal.description

            # Generate weights biased by the hypothesis
            weights = self._generate_candidate_weights()
            if not weights:
                return None

            # Bias weights for the specific skill that's underperforming
            skill_name = best_proposal.skill_name
            if skill_name:
                for pid, conf in weights.items():
                    # Reduce confidence for patterns related to the failing skill
                    # (they're not working well, try something different)
                    weights[pid] = max(0.05, conf * random.uniform(0.5, 0.9))

            channel_timing = self._generate_channel_timing()

            return ShadowCandidate(
                version=f"shadow-hyp-{uuid.uuid4().hex[:8]}",
                weights=weights,
                channel_timing=channel_timing,
                hypothesis=hypothesis,
                created_at=datetime.now(timezone.utc).isoformat(),
                status="testing",
            )

        except Exception as e:
            logger.debug(f"Hypothesis candidate generation failed: {e}")
            return None

    def _generate_candidate_weights(self) -> Dict[str, float]:
        """Perturb current pattern confidences to create candidate weights."""
        from ..types import Domain

        weights: Dict[str, float] = {}
        r = self._config.perturbation_range

        for domain in Domain:
            try:
                patterns = self._semantic.retrieve_patterns(
                    skill_name="*", domain=domain, limit=50,
                )
            except Exception:
                patterns = []

            for p in patterns:
                perturbation = 1.0 + random.uniform(-r, r)
                new_conf = max(0.05, min(0.99, p.confidence * perturbation))
                weights[p.pattern_id] = new_conf

        if not weights:
            logger.debug("No patterns to perturb for shadow candidate")

        return weights

    def _generate_channel_timing(self) -> Dict[str, Dict[str, float]]:
        """Perturb channel timing to explore better measurement windows."""
        try:
            from ..adapters.channels import CHANNEL_REGISTRY
        except ImportError:
            return {}

        channel_timing: Dict[str, Dict[str, float]] = {}
        for channel_id, config in CHANNEL_REGISTRY.items():
            channel_timing[channel_id] = {
                "measurement_window_hours": config.measurement_window_hours * random.uniform(0.75, 1.25),
                "full_measurement_days": int(config.full_measurement_days * random.uniform(0.75, 1.25)),
            }
        return channel_timing

    def _apply_channel_timing(self, channel_timing: Dict[str, Dict[str, float]]):
        """Persist promoted channel timing to Firebase and update in-memory registry."""
        _CHANNEL_TIMING_COLLECTION = "system/intelligence/channel_timing"

        if not self._firebase or not hasattr(self._firebase, "set_document"):
            return

        for channel_id, timing in channel_timing.items():
            try:
                self._firebase.set_document(
                    _CHANNEL_TIMING_COLLECTION,
                    channel_id,
                    {
                        "channel_id": channel_id,
                        "measurement_window_hours": timing.get("measurement_window_hours"),
                        "full_measurement_days": timing.get("full_measurement_days"),
                        "promoted_at": datetime.now(timezone.utc).isoformat(),
                    },
                    merge=True,
                )
            except Exception as e:
                logger.debug(f"Failed to persist channel timing for {channel_id}: {e}")

        # Update in-memory channel registry
        try:
            from ..adapters.channels import CHANNEL_REGISTRY
            for channel_id, timing in channel_timing.items():
                config = CHANNEL_REGISTRY.get(channel_id)
                if config is not None:
                    mw = timing.get("measurement_window_hours")
                    fm = timing.get("full_measurement_days")
                    if mw is not None:
                        config.measurement_window_hours = float(mw)
                    if fm is not None:
                        config.full_measurement_days = int(fm)
            logger.info(f"Updated channel timing for {len(channel_timing)} channels")
        except ImportError:
            pass

    def _apply_weights_to_patterns(self, weights: Dict[str, float]):
        """Apply promoted weights back to semantic patterns."""
        if not hasattr(self._semantic, "update_confidence"):
            logger.debug("Semantic store missing update_confidence; skipping weight apply")
            return

        for pattern_id, confidence in weights.items():
            try:
                self._semantic.update_confidence(pattern_id, confidence)
            except Exception as e:
                logger.debug(f"Could not apply weight for {pattern_id}: {e}")

    def _archive_history(self, entry: Dict[str, Any]):
        """Write a promotion/rejection record."""
        if not self._firebase or not hasattr(self._firebase, "add_document"):
            return
        try:
            self._firebase.add_document(self._HISTORY_COLLECTION, entry)
        except Exception as e:
            logger.debug(f"Failed to archive shadow history: {e}")

    def get_error_delta(self) -> Optional[float]:
        """Current production-vs-candidate error delta (for daily checkpoint)."""
        if not self._candidate or not self._candidate.test_outcomes:
            return None
        outcomes = self._candidate.test_outcomes
        prod = sum(abs(o["production_error"]) for o in outcomes) / len(outcomes)
        cand = sum(abs(o["prediction_error"]) for o in outcomes) / len(outcomes)
        return prod - cand


__all__ = ["ShadowConfig", "ShadowCandidate", "ShadowManager"]
