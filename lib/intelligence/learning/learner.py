"""
MH1 Intelligence Learner

Bayesian learning from outcomes with concept drift detection.
Updates semantic patterns based on prediction accuracy and detects
when the environment has changed (drift), triggering relearning.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING  # noqa: F401

from ..types import Domain, Prediction, Outcome
from ..memory.episodic import EpisodicMemoryStore

if TYPE_CHECKING:
    from ..memory.semantic import SemanticMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class LearningConfig:
    """Configuration for the learning system."""
    learning_rate: float = 0.1
    drift_window_size: int = 20  # Samples for drift detection
    drift_threshold: float = 2.0  # Standard deviations
    relearning_exploration_boost: float = 0.3


class Learner:
    """
    Bayesian learner with concept drift detection.
    
    Updates semantic patterns based on observed outcomes and detects
    when prediction errors indicate environmental changes (concept drift).
    When drift is detected, triggers relearning by reducing pattern
    confidence and boosting exploration.
    """
    
    _ERROR_HISTORY_COLLECTION = "system/intelligence/error_history"
    _PERSIST_EVERY_N = 5  # write to Firebase every N outcomes

    def __init__(
        self,
        episodic_store: EpisodicMemoryStore,
        semantic_store: "SemanticMemoryStore",
        config: Optional[LearningConfig] = None,
        shadow_manager: Optional[Any] = None,
    ):
        """
        Initialize the learner.
        
        Args:
            episodic_store: Store for episodic memories
            semantic_store: Store for semantic patterns
            config: Learning configuration parameters
            shadow_manager: Optional ShadowManager for dual-scoring
        """
        self._episodic = episodic_store
        self._semantic = semantic_store
        self._config = config or LearningConfig()
        self._shadow = shadow_manager
        self._error_history: Dict[str, List[float]] = {}
        self._outcome_counter = 0
        self._load_error_history()
    
    def learn_from_outcome(
        self,
        prediction: Prediction,
        outcome: Outcome,
        learning_weight: float = 1.0,
        checkpoint_day: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Main learning method. Updates patterns based on observed outcomes.
        
        When ``checkpoint_day`` is provided and the matched pattern has an
        ``expected_trajectory``, the error is computed against the trajectory
        point for that checkpoint (not the final target). This prevents
        incorrectly scoring a "spike then recover" strategy as a failure
        at the spike checkpoint.
        
        Args:
            prediction: The prediction that was made
            outcome: The observed outcome
            learning_weight: Weight from ThreeGateScorer's learning_signal_quality.
            checkpoint_day: Which checkpoint day this observation corresponds to
                (e.g. 7, 14, 30). When set, trajectory-aware scoring is used.
            
        Returns:
            Dict with:
            - patterns_updated: int - number of patterns updated
            - drift_detected: bool - whether drift was detected
            - drift_skill: Optional[str] - skill name if drift detected
            - learning_weight: float - weight applied to this update
            - trajectory_scored: bool - whether trajectory scoring was used
        """
        result = {
            "patterns_updated": 0,
            "drift_detected": False,
            "drift_skill": None,
            "learning_weight": learning_weight,
            "trajectory_scored": False,
        }

        # Clamp learning_weight to [0.05, 1.0] to avoid zero-updates
        learning_weight = max(0.05, min(1.0, learning_weight))
        
        # Step 1: Calculate prediction error
        if prediction.expected_baseline == 0:
            expected_ratio = prediction.expected_signal
        else:
            expected_ratio = prediction.expected_signal / prediction.expected_baseline
        
        if outcome.observed_baseline == 0:
            observed_ratio = outcome.observed_signal
        else:
            observed_ratio = outcome.observed_signal / outcome.observed_baseline
        
        error = observed_ratio - expected_ratio

        # Apply learning_weight: scale the effective observed_ratio toward
        # the expected value for low-quality signals (locked parameters).
        weighted_observed_ratio = (
            expected_ratio + (observed_ratio - expected_ratio) * learning_weight
        )
        
        # Step 2: Determine success
        success = outcome.goal_completed
        
        # Step 3: Update each pattern used in the prediction
        # When checkpoint_day is set and the pattern has a trajectory,
        # score against the trajectory point instead of the final target.
        for pattern_id in prediction.patterns_used:
            trajectory_used = False
            if checkpoint_day and hasattr(self._semantic, 'get_pattern'):
                try:
                    pattern = self._semantic.get_pattern(pattern_id, prediction.domain)
                    if pattern and pattern.expected_trajectory:
                        tp = min(
                            pattern.expected_trajectory,
                            key=lambda t: abs(t.checkpoint_days - checkpoint_day),
                        )
                        trajectory_expected = tp.expected_ratio
                        trajectory_error = observed_ratio - trajectory_expected

                        # Update only this trajectory point with EMA
                        tp.expected_ratio = (
                            0.9 * tp.expected_ratio + 0.1 * observed_ratio
                        )
                        tp.observation_count += 1
                        tp.confidence = min(1.0, tp.observation_count / 10)

                        # Use trajectory-adjusted observed_ratio for pattern update
                        weighted_observed_ratio = (
                            trajectory_expected
                            + (observed_ratio - trajectory_expected) * learning_weight
                        )
                        error = trajectory_error
                        trajectory_used = True
                        result["trajectory_scored"] = True
                except Exception as e:
                    logger.debug(f"Trajectory scoring failed for {pattern_id}: {e}")

            self._semantic.update_from_outcome(
                pattern_id=pattern_id,
                domain=prediction.domain,
                success=success,
                observed_ratio=weighted_observed_ratio
            )
            result["patterns_updated"] += 1
        
        # Step 4: Check for concept drift
        drift_key = f"{prediction.skill_name}:{prediction.domain.value}"
        drift_detected = self._check_drift(drift_key, error)
        
        # Step 5: Trigger relearning if drift detected
        if drift_detected:
            result["drift_detected"] = True
            result["drift_skill"] = prediction.skill_name
            self._trigger_relearning(prediction.skill_name, prediction.domain)

        # Step 6: Shadow dual-scoring (V4)
        self._outcome_counter += 1
        if self._shadow:
            try:
                production_error = abs(error)
                candidate_error = abs(error)

                candidate = self._shadow.active_candidate
                if candidate and candidate.weights:
                    candidate_expected = self._score_with_weights(
                        prediction, candidate.weights
                    )
                    if candidate_expected is not None:
                        candidate_error = abs(observed_ratio - candidate_expected)

                self._shadow.dual_score(
                    prediction_error=candidate_error,
                    production_error=production_error,
                )
                result["shadow_scored"] = True

                eval_interval = getattr(
                    self._shadow, '_config', None
                )
                if eval_interval and self._outcome_counter % eval_interval.evaluation_interval == 0:
                    all_errors = self._error_history.get(drift_key, [])
                    self._shadow.maybe_spawn_candidate(all_errors)
            except Exception as e:
                logger.debug(f"Shadow scoring failed: {e}")

        # Step 7: Periodically persist error history to Firebase
        if self._outcome_counter % self._PERSIST_EVERY_N == 0:
            self._persist_error_history()

        return result
    
    def _check_drift(self, key: str, error: float) -> bool:
        """
        Detect concept drift using sliding window comparison.
        
        Compares the mean error of recent samples against older samples.
        If the difference exceeds drift_threshold * std_dev, drift is detected.
        
        Args:
            key: The skill:domain key for tracking errors
            error: The prediction error to add
            
        Returns:
            True if drift is detected, False otherwise
        """
        # Step 1: Add error to history
        if key not in self._error_history:
            self._error_history[key] = []
        
        self._error_history[key].append(error)
        
        # Step 2: Keep only last drift_window_size * 2 errors
        max_size = self._config.drift_window_size * 2
        if len(self._error_history[key]) > max_size:
            self._error_history[key] = self._error_history[key][-max_size:]
        
        errors = self._error_history[key]
        
        # Step 3: If not enough data, return False
        if len(errors) < self._config.drift_window_size:
            return False
        
        # Step 4: Split errors into recent half and older half
        midpoint = len(errors) // 2
        older_half = errors[:midpoint]
        recent_half = errors[midpoint:]
        
        # Step 5: Calculate means of each half
        older_mean = sum(older_half) / len(older_half) if older_half else 0.0
        recent_mean = sum(recent_half) / len(recent_half) if recent_half else 0.0
        
        # Step 6: Calculate overall standard deviation
        overall_mean = sum(errors) / len(errors)
        variance = sum((e - overall_mean) ** 2 for e in errors) / len(errors)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0
        
        # Step 7: Check if drift threshold exceeded
        if std_dev > 0:
            mean_diff = abs(recent_mean - older_mean)
            threshold = self._config.drift_threshold * std_dev
            
            if mean_diff > threshold:
                logger.warning(
                    f"Concept drift detected for {key}: "
                    f"mean_diff={mean_diff:.4f}, threshold={threshold:.4f}, "
                    f"recent_mean={recent_mean:.4f}, older_mean={older_mean:.4f}"
                )
                return True
        
        return False
    
    def _trigger_relearning(self, skill_name: str, domain: Domain):
        """
        Trigger relearning when concept drift is detected.
        
        Reduces confidence of all patterns for this skill/domain and
        clears the error history to start fresh.
        
        Args:
            skill_name: Name of the skill experiencing drift
            domain: Domain experiencing drift
        """
        logger.info(
            f"Triggering relearning for skill={skill_name}, domain={domain.value}"
        )
        
        # Step 1: Get all patterns for this skill/domain
        patterns = self._semantic.retrieve_patterns(
            skill_name=skill_name,
            domain=domain,
        )
        
        # Step 2: Reduce confidence of all patterns by 50% (min 0.1)
        # We do this by treating each pattern as having a failure
        for pattern in patterns:
            # Update as failure to reduce confidence
            # This will reduce confidence through Bayesian update
            self._semantic.update_from_outcome(
                pattern_id=pattern.pattern_id,
                domain=domain,
                success=False,
                observed_ratio=pattern.expected_value * 0.5
            )
        
        logger.info(
            f"Reduced confidence for {len(patterns)} patterns in "
            f"skill={skill_name}, domain={domain.value}"
        )
        
        # Step 3: Clear error history for this skill:domain
        drift_key = f"{skill_name}:{domain.value}"
        if drift_key in self._error_history:
            del self._error_history[drift_key]
            logger.debug(f"Cleared error history for {drift_key}")
        self._persist_error_history()

    def _score_with_weights(
        self, prediction: Prediction, weights: Dict[str, float]
    ) -> Optional[float]:
        """Compute expected ratio using candidate shadow weights instead of stored pattern confidence."""
        if not prediction.patterns_used:
            return None
        weighted_sum = 0.0
        weight_total = 0.0
        for pid in prediction.patterns_used:
            conf = weights.get(pid)
            if conf is None:
                continue
            try:
                patterns = self._semantic.retrieve_patterns(
                    skill_name=prediction.skill_name,
                    domain=prediction.domain,
                    limit=100,
                )
                for p in patterns:
                    if p.pattern_id == pid:
                        weighted_sum += conf * p.expected_value
                        weight_total += conf
                        break
            except Exception:
                continue
        if weight_total == 0:
            return None
        return weighted_sum / weight_total

    def _get_firebase(self):
        """Access Firebase client via the episodic store."""
        fb = getattr(self._episodic, '_firebase', None)
        if fb and hasattr(fb, 'set_document'):
            return fb
        return None

    def _load_error_history(self):
        """Load persisted error history from Firebase on init."""
        fb = self._get_firebase()
        if not fb:
            return
        try:
            docs = fb.get_collection(collection=self._ERROR_HISTORY_COLLECTION)
            if not docs:
                return
            for doc in docs:
                key = doc.get("key", doc.get("_id", ""))
                errors = doc.get("errors", [])
                if key and isinstance(errors, list):
                    self._error_history[key] = errors
            if self._error_history:
                logger.info(
                    f"Loaded error history for {len(self._error_history)} skill:domain pairs"
                )
        except Exception as e:
            logger.debug(f"Could not load error history: {e}")

    def _persist_error_history(self):
        """Persist current error history to Firebase."""
        fb = self._get_firebase()
        if not fb:
            return
        for key, errors in self._error_history.items():
            try:
                doc_id = key.replace(":", "_")
                fb.set_document(
                    collection=self._ERROR_HISTORY_COLLECTION,
                    doc_id=doc_id,
                    data={"key": key, "errors": errors[-100:]},
                )
            except Exception as e:
                logger.debug(f"Failed to persist error history for {key}: {e}")


__all__ = [
    "LearningConfig",
    "Learner",
]
