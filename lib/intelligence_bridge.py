"""
Intelligence Bridge - Simplified interface between runners and intelligence system.

This module provides a clean, easy-to-use interface for skill and workflow runners
to interact with the MH1 Intelligence System. It handles:

- Domain inference for all 64 skills
- Guidance retrieval with sensible defaults
- Prediction tracking and outcome recording
- Memory consolidation coordination

Usage:
    from lib.intelligence_bridge import IntelligenceBridge, SkillGuidance

    bridge = IntelligenceBridge()

    # Before skill execution
    guidance = bridge.get_skill_guidance("lifecycle-audit", "acme-corp", {"segment": "enterprise"})
    tracking_id = bridge.start_tracking("lifecycle-audit", "acme-corp", guidance)

    # ... run skill ...

    # After skill execution
    result = bridge.complete_tracking(tracking_id, skill_result, {"contacts_processed": 5000})
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from lib.intelligence import IntelligenceEngine

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SkillGuidance:
    """
    Guidance for skill execution.

    Contains recommended parameters, confidence levels, and metadata about
    whether this is an exploration or exploitation decision.

    Attributes:
        parameters: Recommended parameter values for the skill
        confidence: Confidence in the recommendation (0-1)
        expected_value: Expected Signal/Baseline ratio
        is_exploration: Whether this is an exploratory recommendation
        exploration_reason: Why exploration was chosen (if applicable)
        patterns_used: IDs of semantic patterns that informed guidance
        domain: Business domain for the skill
    """
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    expected_value: float = 1.0
    is_exploration: bool = False
    exploration_reason: str = ""
    patterns_used: List[str] = field(default_factory=list)
    domain: "Domain" = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "parameters": self.parameters,
            "confidence": self.confidence,
            "expected_value": self.expected_value,
            "is_exploration": self.is_exploration,
            "exploration_reason": self.exploration_reason,
            "patterns_used": self.patterns_used,
            "domain": self.domain.value if self.domain else "generic",
        }

    @classmethod
    def from_guidance(cls, guidance: "Guidance", domain: "Domain") -> "SkillGuidance":
        """Create SkillGuidance from intelligence system Guidance object."""
        return cls(
            parameters=guidance.parameters,
            confidence=guidance.confidence,
            expected_value=1.0 - guidance.uncertainty,  # Convert uncertainty to expected value
            is_exploration=guidance.is_exploration,
            exploration_reason=guidance.exploration_reason,
            patterns_used=guidance.patterns_used,
            domain=domain,
        )


@dataclass
class LearningResult:
    """
    Result from recording an outcome.

    Attributes:
        prediction_id: ID of the prediction that was completed
        patterns_updated: Number of semantic patterns updated
        drift_detected: Whether concept drift was detected
        episode_stored: Whether the episode was stored to episodic memory
    """
    prediction_id: str = ""
    patterns_updated: int = 0
    drift_detected: bool = False
    episode_stored: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "prediction_id": self.prediction_id,
            "patterns_updated": self.patterns_updated,
            "drift_detected": self.drift_detected,
            "episode_stored": self.episode_stored,
        }


# =============================================================================
# Domain Enum Import (lazy to avoid circular imports)
# =============================================================================

_cached_domain_enum = None
_domain_import_failed = False


def _get_domain_enum():
    """
    Lazy import of Domain enum to avoid circular imports.

    Returns the Domain enum class, or a fallback MockDomain class if
    the intelligence module is unavailable.
    """
    global _cached_domain_enum, _domain_import_failed

    if _cached_domain_enum is not None:
        return _cached_domain_enum

    if _domain_import_failed:
        return _MockDomain

    try:
        from lib.intelligence.types import Domain
        _cached_domain_enum = Domain
        return Domain
    except ImportError:
        _domain_import_failed = True
        logger.warning("Failed to import Domain enum, using MockDomain")
        return _MockDomain


class _MockDomainMeta(type):
    """Metaclass to support Domain.CONTENT syntax."""
    _instances = {}

    def __getattr__(cls, name):
        name_lower = name.lower()
        if name_lower in ("content", "revenue", "health", "campaign", "generic"):
            if name_lower not in cls._instances:
                cls._instances[name_lower] = cls(name_lower)
            return cls._instances[name_lower]
        raise AttributeError(f"'{cls.__name__}' has no attribute '{name}'")


class _MockDomain(metaclass=_MockDomainMeta):
    """
    Mock Domain enum for when the intelligence module is unavailable.

    This allows the bridge to function without the full intelligence system.
    Supports both Domain("content") and Domain.CONTENT syntax.
    """

    def __init__(self, value: str):
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other):
        if isinstance(other, _MockDomain):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return False

    def __hash__(self):
        return hash(self._value)

    def __repr__(self):
        return f"Domain.{self._value.upper()}"


# =============================================================================
# Intelligence Bridge
# =============================================================================

class IntelligenceBridge:
    """
    Wrapper that makes it easy for runners to use the intelligence system.

    This bridge provides a simplified interface for:
    - Getting guidance before skill execution
    - Tracking predictions and outcomes
    - Running memory consolidation

    It automatically handles domain inference for all 49 skills and provides
    sensible defaults when the intelligence system is unavailable.

    Example:
        >>> bridge = IntelligenceBridge()
        >>>
        >>> # Get guidance before running a skill
        >>> guidance = bridge.get_skill_guidance(
        ...     skill_name="lifecycle-audit",
        ...     client_id="acme-corp",
        ...     inputs={"segment": "enterprise"}
        ... )
        >>>
        >>> # Start tracking
        >>> tracking_id = bridge.start_tracking("lifecycle-audit", "acme-corp", guidance)
        >>>
        >>> # ... run skill ...
        >>>
        >>> # Record outcome
        >>> result = bridge.complete_tracking(
        ...     tracking_id,
        ...     skill_result,
        ...     metrics={"contacts_processed": 5000}
        ... )
    """

    # Domain mapping for ALL 64 skills
    # Organized by domain for clarity
    SKILL_DOMAINS = {
        # =====================================================================
        # REVENUE Domain - Deal tracking, pipeline, sales performance
        # =====================================================================
        "lifecycle-audit": "revenue",
        "churn-prediction": "revenue",
        "at-risk-detection": "revenue",
        "dormant-detection": "revenue",
        "reactivation-detection": "revenue",
        "cohort-retention-analysis": "revenue",
        "deal-velocity": "revenue",
        "pipeline-analysis": "revenue",
        "sales-rep-performance": "revenue",
        "upsell-candidates": "revenue",
        "renewal-tracker": "revenue",
        "conversion-funnel": "revenue",
        "qualify-leads": "revenue",
        "account-360": "revenue",

        # =====================================================================
        # HEALTH Domain - Customer health, engagement, retention
        # =====================================================================
        "engagement-velocity": "health",
        "call-analytics": "health",
        "data-quality-audit": "health",

        # =====================================================================
        # CONTENT Domain - Content creation, voice, research
        # =====================================================================
        "brand-voice": "content",
        "positioning-angles": "content",
        "direct-response-copy": "content",
        "seo-content": "content",
        "lifecycle-communications-sequences": "content",
        "lead-magnet": "content",
        "newsletter-builder": "content",
        "content-atomizer": "content",
        "extract-founder-voice": "content",
        "extract-writing-guideline": "content",
        "extract-pov": "content",
        "extract-audience-persona": "content",
        "extract-company-profile": "content",
        "ghostwrite-content": "content",
        "email-copy-generator": "content",
        "cohort-email-builder": "content",
        "generate-interview-questions": "content",
        "incorporate-interview-results": "content",
        "generate-context-summary": "content",
        "create-assignment-brief": "content",
        "research-founder": "content",
        "research-company": "content",
        "research-competitors": "content",
        "icp-historical-analysis": "content",

        # =====================================================================
        # CAMPAIGN Domain - Social listening, marketing campaigns
        # =====================================================================
        "social-listening-collect": "campaign",
        "linkedin-keyword-search": "campaign",
        "linkedin-browser-scrape": "campaign",
        "twitter-keyword-search": "campaign",
        "reddit-keyword-search": "campaign",
        "upload-posts-to-notion": "campaign",
        "playbook-executor": "campaign",
        "keyword-research": "campaign",
        "cold-email-personalization": "campaign",
        "foreplay-ads": "campaign",
        "bright-crawler": "campaign",

        # =====================================================================
        # GENERIC Domain - Infrastructure, utilities, meta-skills
        # =====================================================================
        "crm-discovery": "generic",
        "data-warehouse-discovery": "generic",
        "identity-mapping": "generic",
        "needs-assessment": "generic",
        "gtm-engineering": "generic",
        "dataforseo": "generic",
        "client-onboarding": "generic",
        "skill-builder": "generic",
        "marketing-orchestrator": "generic",
        "get-client": "generic",
        "firestore-nav": "generic",
        "firebase-bulk-upload": "generic",
        "artifact-manager": "generic",
        "platform-retrieval": "generic",
    }

    # Default domain for unknown skills
    DEFAULT_DOMAIN = "content"

    def __init__(self, engine: "IntelligenceEngine" = None):
        """
        Initialize the Intelligence Bridge.

        Args:
            engine: Optional IntelligenceEngine instance. If not provided,
                    will be lazy-loaded when first needed.
        """
        self._engine = engine
        self._engine_loaded = engine is not None
        self._tracking: Dict[str, Dict[str, Any]] = {}

        logger.debug("IntelligenceBridge initialized")

    @property
    def engine(self) -> Optional["IntelligenceEngine"]:
        """
        Lazy-load the IntelligenceEngine.

        Returns None if the intelligence system is unavailable.
        """
        if not self._engine_loaded:
            self._engine_loaded = True
            try:
                from lib.intelligence import IntelligenceEngine
                self._engine = IntelligenceEngine()
                logger.debug("IntelligenceEngine loaded successfully")
            except ImportError as e:
                logger.warning(f"Failed to import IntelligenceEngine: {e}")
                self._engine = None
            except Exception as e:
                logger.error(f"Failed to initialize IntelligenceEngine: {e}")
                self._engine = None

        return self._engine

    def infer_domain(self, skill_name: str) -> "Domain":
        """
        Get domain for a skill.

        Uses the SKILL_DOMAINS mapping to determine the appropriate domain
        for a skill. Falls back to DEFAULT_DOMAIN (content) for unknown skills.

        Args:
            skill_name: Name of the skill

        Returns:
            Domain enum value

        Example:
            >>> bridge.infer_domain("lifecycle-audit")
            Domain.REVENUE
            >>> bridge.infer_domain("unknown-skill")
            Domain.CONTENT
        """
        Domain = _get_domain_enum()

        domain_str = self.SKILL_DOMAINS.get(skill_name, self.DEFAULT_DOMAIN)

        try:
            return Domain(domain_str)
        except ValueError:
            logger.warning(f"Invalid domain '{domain_str}' for skill '{skill_name}', using CONTENT")
            return Domain.CONTENT

    def get_skill_guidance(
        self,
        skill_name: str,
        client_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        phase0_metrics: Optional[Dict[str, Any]] = None,
    ) -> SkillGuidance:
        """
        Get guidance before skill execution.

        Queries the intelligence system for learned patterns and recommendations.
        If the intelligence system is unavailable, returns default guidance.

        When Phase 0 computed_metrics are available, they are merged into the
        context so the Predictor can match patterns against actual CRM data
        (e.g., current churn rate, lifecycle distribution, total contacts).

        Args:
            skill_name: Name of the skill to get guidance for
            client_id: Client/tenant identifier
            inputs: Optional input context (e.g., segment, time of day)
            phase0_metrics: Optional computed_metrics.json from Phase 0 —
                provides real data context for smarter pattern matching.

        Returns:
            SkillGuidance with recommended parameters and confidence

        Example:
            >>> guidance = bridge.get_skill_guidance(
            ...     "lifecycle-audit",
            ...     "acme-corp",
            ...     {"segment": "enterprise"},
            ...     phase0_metrics={"total_records": 45000, "churn_rate": 0.12}
            ... )
            >>> print(f"Confidence: {guidance.confidence}")
            >>> print(f"Is exploration: {guidance.is_exploration}")
        """
        domain = self.infer_domain(skill_name)
        inputs = inputs or {}

        # ── Enrich context with Phase 0 data ──────────────────────────────
        # This lets the Predictor match patterns against real client data
        # instead of relying on hardcoded defaults.  Phase 0 metrics contain
        # actual lifecycle distributions, churn rates, record counts, etc.
        if phase0_metrics:
            inputs = dict(inputs)  # don't mutate caller's dict
            # Flatten key Phase 0 metrics into the context for pattern matching
            for key in (
                "total_records", "churn_rate", "retention_rate",
                "active_rate", "dormant_rate", "at_risk_rate",
                "avg_deal_size", "pipeline_velocity", "conversion_rate",
                "total_contacts", "total_deals", "total_revenue",
                "engagement_rate", "open_rate", "click_rate",
            ):
                if key in phase0_metrics:
                    inputs[f"phase0_{key}"] = phase0_metrics[key]
            # Store the full metrics under a namespaced key for adapters
            inputs["_phase0_computed_metrics"] = phase0_metrics

        # If engine is unavailable, return default guidance
        if self.engine is None:
            logger.debug(f"Intelligence engine unavailable, returning default guidance for {skill_name}")
            return SkillGuidance(
                parameters={},
                confidence=0.5,
                expected_value=1.0,
                is_exploration=True,
                exploration_reason="intelligence_unavailable",
                patterns_used=[],
                domain=domain,
            )

        try:
            # Get guidance from intelligence system
            guidance = self.engine.get_guidance(
                skill_name=skill_name,
                tenant_id=client_id,
                domain=domain,
                context=inputs,
            )

            return SkillGuidance.from_guidance(guidance, domain)

        except Exception as e:
            logger.warning(f"Failed to get guidance for {skill_name}: {e}")
            return SkillGuidance(
                parameters={},
                confidence=0.5,
                expected_value=1.0,
                is_exploration=True,
                exploration_reason=f"guidance_error:{str(e)[:50]}",
                patterns_used=[],
                domain=domain,
            )

    def start_tracking(
        self,
        skill_name: str,
        client_id: str,
        guidance: SkillGuidance,
        expected_signal: float = 1.0,
        expected_baseline: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register prediction, returns prediction_id.

        Call this before skill execution to enable learning. The returned
        prediction_id should be passed to complete_tracking() after execution.

        Args:
            skill_name: Name of the skill being executed
            client_id: Client/tenant identifier
            guidance: Guidance object from get_skill_guidance()
            expected_signal: Expected outcome signal (default 1.0)
            expected_baseline: Expected baseline for comparison (default 1.0)
            context: Additional context at prediction time

        Returns:
            prediction_id for use with complete_tracking()

        Example:
            >>> guidance = bridge.get_skill_guidance("lifecycle-audit", "acme-corp")
            >>> tracking_id = bridge.start_tracking(
            ...     "lifecycle-audit",
            ...     "acme-corp",
            ...     guidance,
            ...     expected_signal=50,  # expect to find 50 issues
            ...     expected_baseline=1.0
            ... )
        """
        context = context or {}

        # Generate tracking ID even if engine is unavailable
        tracking_id = str(uuid.uuid4())[:12]

        # Store tracking info locally
        self._tracking[tracking_id] = {
            "skill_name": skill_name,
            "client_id": client_id,
            "guidance": guidance,
            "expected_signal": expected_signal,
            "expected_baseline": expected_baseline,
            "context": context,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "prediction_id": None,
        }

        # If engine is unavailable, return tracking ID without registering prediction
        if self.engine is None:
            logger.debug(f"Intelligence engine unavailable, using local tracking for {skill_name}")
            return tracking_id

        try:
            # Register prediction with intelligence system
            from lib.intelligence import Guidance as IntelGuidance

            # Convert SkillGuidance back to Guidance for the engine
            intel_guidance = IntelGuidance(
                parameters=guidance.parameters,
                confidence=guidance.confidence,
                uncertainty=1.0 - guidance.expected_value,
                is_exploration=guidance.is_exploration,
                exploration_reason=guidance.exploration_reason,
                patterns_used=guidance.patterns_used,
            )

            prediction_id = self.engine.register_prediction(
                skill_name=skill_name,
                tenant_id=client_id,
                domain=guidance.domain,
                expected_signal=expected_signal,
                expected_baseline=expected_baseline,
                confidence=guidance.confidence,
                context=context,
                guidance=intel_guidance,
            )

            # Store the prediction ID
            self._tracking[tracking_id]["prediction_id"] = prediction_id

            logger.debug(f"Started tracking {skill_name} with prediction_id={prediction_id}")

        except Exception as e:
            logger.warning(f"Failed to register prediction for {skill_name}: {e}")

        return tracking_id

    def complete_tracking(
        self,
        tracking_id: str,
        result: Any,
        metrics: Optional[Dict[str, Any]] = None,
        goal_completed: bool = None,
        business_impact: float = 0.0,
        deferred: bool = False,
    ) -> LearningResult:
        """
        Record outcome after execution.

        Call this after skill execution completes to enable learning.

        When ``deferred=True``, the episode is stored to episodic memory
        but the learning path (pattern updates, shadow dual-scoring, drift
        detection) is **skipped**. Real learning happens later via
        ``close_deferred_outcome()`` when 7-day platform performance data
        arrives. The immediate ``business_impact`` is stored as a
        diagnostic ``generation_score`` only.

        Args:
            tracking_id: ID returned from start_tracking()
            result: The skill execution result (used to infer observed_signal)
            metrics: Additional metrics about the outcome
            goal_completed: Whether the skill goal was achieved (auto-inferred if None)
            business_impact: Quantified business impact (optional)
            deferred: If True, skip pattern updates and shadow scoring.
                The outcome will be resolved later via close_deferred_outcome().

        Returns:
            LearningResult with information about the learning update
        """
        metrics = metrics or {}

        # Get tracking info
        tracking_info = self._tracking.pop(tracking_id, None)
        if tracking_info is None:
            logger.warning(f"Tracking ID {tracking_id} not found")
            return LearningResult(
                prediction_id=tracking_id,
                patterns_updated=0,
                drift_detected=False,
                episode_stored=False,
            )

        # Infer observed signal from result
        observed_signal = self._infer_signal(result, metrics)

        # Extract Phase 0 metrics if this is a Phase 0 node
        phase0_metrics = self._extract_phase0_metrics(result, metrics)
        if phase0_metrics:
            metrics = dict(metrics)
            metrics["_phase0_computed_metrics"] = phase0_metrics
            logger.info(
                f"Phase 0 metrics captured for tracking {tracking_id}: "
                f"{phase0_metrics.get('total_records', '?')} records"
            )

        if goal_completed is None:
            goal_completed = self._infer_goal_completion(result)

        prediction_id = tracking_info.get("prediction_id")
        if prediction_id is None or self.engine is None:
            logger.debug(f"No prediction to complete for tracking {tracking_id}")
            return LearningResult(
                prediction_id=tracking_id,
                patterns_updated=0,
                drift_detected=False,
                episode_stored=False,
            )

        try:
            if deferred:
                return self._complete_deferred(
                    prediction_id, tracking_info, observed_signal,
                    goal_completed, business_impact, metrics,
                )
            else:
                return self._complete_immediate(
                    prediction_id, tracking_info, observed_signal,
                    goal_completed, business_impact, metrics,
                )
        except Exception as e:
            logger.warning(f"Failed to complete tracking for {tracking_id}: {e}")
            return LearningResult(
                prediction_id=prediction_id,
                patterns_updated=0,
                drift_detected=False,
                episode_stored=False,
            )

    def _complete_immediate(
        self,
        prediction_id: str,
        tracking_info: Dict[str, Any],
        observed_signal: float,
        goal_completed: bool,
        business_impact: float,
        metrics: Dict[str, Any],
    ) -> LearningResult:
        """Full learning path: store episode + update patterns + shadow scoring."""
        outcome_result = self.engine.record_outcome(
            prediction_id=prediction_id,
            observed_signal=observed_signal,
            observed_baseline=tracking_info.get("expected_baseline", 1.0),
            goal_completed=goal_completed,
            business_impact=business_impact,
            metadata=metrics,
        )
        learning_result = outcome_result.get("learning_result", {})
        return LearningResult(
            prediction_id=prediction_id,
            patterns_updated=learning_result.get("patterns_updated", 0) if isinstance(learning_result, dict) else 0,
            drift_detected=learning_result.get("drift_detected", False) if isinstance(learning_result, dict) else False,
            episode_stored=outcome_result.get("success", False),
        )

    def _complete_deferred(
        self,
        prediction_id: str,
        tracking_info: Dict[str, Any],
        observed_signal: float,
        goal_completed: bool,
        business_impact: float,
        metrics: Dict[str, Any],
    ) -> LearningResult:
        """
        Deferred path: store episode to episodic memory but skip learning.

        The generation_score (business_impact) is recorded as metadata on
        the episode for diagnostic purposes. Real learning happens when
        close_deferred_outcome() is called with platform performance data.
        """
        try:
            outcome_result = self.engine.record_outcome(
                prediction_id=prediction_id,
                observed_signal=observed_signal,
                observed_baseline=tracking_info.get("expected_baseline", 1.0),
                goal_completed=goal_completed,
                business_impact=0.0,
                metadata={**metrics, "_deferred": True, "_generation_score": business_impact},
            )
            logger.info(
                f"Deferred outcome recorded for {prediction_id} "
                f"(generation_score={business_impact:.2f}, learning skipped)"
            )
            return LearningResult(
                prediction_id=prediction_id,
                patterns_updated=0,
                drift_detected=False,
                episode_stored=outcome_result.get("success", False),
            )
        except Exception as e:
            logger.warning(f"Deferred tracking failed for {prediction_id}: {e}")
            return LearningResult(
                prediction_id=prediction_id,
                patterns_updated=0,
                drift_detected=False,
                episode_stored=False,
            )

    def close_deferred_outcome(
        self,
        prediction_id: str,
        client_id: str,
        observed_signal: float,
        business_impact: float,
        platform_metrics: Optional[Dict[str, Any]] = None,
        projection_classification: Optional[str] = None,
    ) -> LearningResult:
        """
        Close a deferred outcome with real-world performance data.

        Called by the outcome_checkpoint_cron after 7 days of platform
        data collection. This triggers the full learning path that was
        skipped during the initial deferred completion.

        Args:
            prediction_id: The original prediction ID.
            client_id: The client/tenant this prediction was for.
            observed_signal: Real-world outcome signal (composite score).
            business_impact: Quantified business impact from platform data.
            platform_metrics: Raw platform metrics dict for metadata.
            projection_classification: "under_projection", "over_projection",
                or "accurate_projection".

        Returns:
            LearningResult from the full learning path.
        """
        if self.engine is None:
            logger.warning("Engine unavailable for deferred outcome closure")
            return LearningResult(prediction_id=prediction_id)

        try:
            from lib.intelligence.outcomes.pending_store import PendingOutcomeStore
            from lib.intelligence.types import Prediction, Outcome
        except ImportError:
            logger.error("Pending outcome store not available")
            return LearningResult(prediction_id=prediction_id)

        try:
            fb = self.engine._firebase
            if not fb:
                logger.error("Firebase not available for deferred outcome")
                return LearningResult(prediction_id=prediction_id)

            store = PendingOutcomeStore(fb)
            pending = store.get(client_id, prediction_id)
            if not pending:
                logger.warning(f"Pending outcome {prediction_id} not found for client {client_id}")
                return LearningResult(prediction_id=prediction_id)

            prediction = Prediction.from_dict(pending.prediction)

            metadata = {
                "_deferred_outcome": True,
                "_projection_classification": projection_classification,
                "_platform_metrics": platform_metrics or {},
                "_generation_score": pending.generation_score,
                "_delivery_metadata": pending.delivery_metadata,
            }

            outcome = Outcome(
                prediction_id=prediction_id,
                observed_signal=observed_signal,
                observed_baseline=prediction.expected_baseline,
                goal_completed=business_impact > 0.3,
                business_impact=business_impact,
                metadata=metadata,
            )

            episode = self.engine.working.complete_prediction(prediction_id, outcome)
            if episode is None:
                self.engine.working.register_prediction(prediction)
                episode = self.engine.working.complete_prediction(prediction_id, outcome)

            if episode:
                try:
                    self.engine.episodic.store(episode=episode)
                except Exception as e:
                    logger.error(f"Failed to store deferred episode: {e}")

            learning_result = self.engine.learner.learn_from_outcome(
                prediction=prediction,
                outcome=outcome,
            )

            logger.info(
                f"Deferred outcome closed for {prediction_id}: "
                f"classification={projection_classification}, "
                f"patterns_updated={learning_result.get('patterns_updated', 0)}"
            )

            return LearningResult(
                prediction_id=prediction_id,
                patterns_updated=learning_result.get("patterns_updated", 0),
                drift_detected=learning_result.get("drift_detected", False),
                episode_stored=True,
            )

        except Exception as e:
            logger.error(f"Failed to close deferred outcome {prediction_id}: {e}")
            return LearningResult(prediction_id=prediction_id)

    def run_consolidation(self, client_id: Optional[str] = None) -> Dict[str, int]:
        """
        Run memory consolidation.

        Consolidation promotes memories from lower to higher memory layers:
        - Decays episodic memories over time
        - Promotes decayed episodes to semantic patterns
        - Archives stale semantic patterns
        - Promotes cross-skill patterns to procedural knowledge

        This should be run periodically (e.g., daily) to maintain
        memory health and enable long-term learning.

        Args:
            client_id: Optional client to consolidate. If None, all clients.

        Returns:
            Statistics dict with consolidation metrics

        Example:
            >>> stats = bridge.run_consolidation("acme-corp")
            >>> print(f"Episodes consolidated: {stats.get('episodes_consolidated', 0)}")
        """
        if self.engine is None:
            logger.warning("Intelligence engine unavailable, skipping consolidation")
            return {
                "episodic_decayed": 0,
                "episodes_consolidated": 0,
                "patterns_created": 0,
                "patterns_updated": 0,
                "patterns_archived": 0,
                "procedural_created": 0,
            }

        try:
            return self.engine.run_consolidation(tenant_id=client_id)
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
            return {
                "episodic_decayed": 0,
                "episodes_consolidated": 0,
                "patterns_created": 0,
                "patterns_updated": 0,
                "patterns_archived": 0,
                "procedural_created": 0,
                "error": str(e),
            }

    def _infer_signal(self, result: Any, metrics: Dict[str, Any]) -> float:
        """
        Infer observed signal from skill result.

        Attempts to extract a meaningful signal value from the result:
        1. Check for Phase 0 computed_metrics (rich deterministic data)
        2. Check for explicit 'signal' key in metrics
        3. Check for common result keys (count, total, score, etc.)
        4. Check result dict for numeric values
        5. Default to 1.0 if unable to infer
        """
        # ── Phase 0 computed_metrics ──────────────────────────────────────
        # Phase 0 produces deterministic data files; the signal is the
        # data completeness/quality score, not a single numeric metric.
        phase0_metrics = self._extract_phase0_metrics(result, metrics)
        if phase0_metrics:
            return self._signal_from_phase0(phase0_metrics)

        # Check metrics first
        if "signal" in metrics:
            return float(metrics["signal"])
        if "observed_signal" in metrics:
            return float(metrics["observed_signal"])
        if "count" in metrics:
            return float(metrics["count"])
        if "total" in metrics:
            return float(metrics["total"])
        if "score" in metrics:
            return float(metrics["score"])

        # Check result if it's a dict
        if isinstance(result, dict):
            for key in ["signal", "count", "total", "score", "value", "result"]:
                if key in result and isinstance(result[key], (int, float)):
                    return float(result[key])

            # Check for common output patterns
            output = result.get("output", {})
            if isinstance(output, dict):
                for key in ["signal", "count", "total", "score", "contacts", "accounts", "issues"]:
                    if key in output and isinstance(output[key], (int, float)):
                        return float(output[key])

                # Check if output is a list and return length
                for key in ["results", "items", "records", "contacts", "accounts"]:
                    if key in output and isinstance(output[key], list):
                        return float(len(output[key]))

        # Check if result is a list
        if isinstance(result, list):
            return float(len(result))

        # Check if result is a number
        if isinstance(result, (int, float)):
            return float(result)

        # Default
        return 1.0

    # ── Phase 0 helpers ───────────────────────────────────────────────────

    @staticmethod
    def _extract_phase0_metrics(
        result: Any, metrics: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect and extract Phase 0 computed_metrics from a result.

        Phase 0 nodes produce ``computed_metrics.json`` in their outputs.
        This helper looks for it in the standard locations:
        - ``result["files"]["computed_metrics.json"]`` (sandbox output capture)
        - ``metrics["computed_metrics"]`` (engine-level injection)
        - ``result["output"]["computed_metrics"]``

        Returns the parsed dict or None if this isn't a Phase 0 result.
        """
        import json as _json

        # Location 1: result.files dict (sandbox captures output files here)
        if isinstance(result, dict):
            files = result.get("files", {})
            if isinstance(files, dict) and "computed_metrics.json" in files:
                raw = files["computed_metrics.json"]
                if isinstance(raw, str):
                    try:
                        return _json.loads(raw)
                    except (ValueError, TypeError):
                        pass
                elif isinstance(raw, dict):
                    return raw

        # Location 2: metrics dict
        if isinstance(metrics, dict) and "computed_metrics" in metrics:
            cm = metrics["computed_metrics"]
            if isinstance(cm, dict):
                return cm

        # Location 3: result.output nested dict
        if isinstance(result, dict):
            output = result.get("output", {})
            if isinstance(output, dict) and "computed_metrics" in output:
                cm = output["computed_metrics"]
                if isinstance(cm, dict):
                    return cm

        return None

    @staticmethod
    def _signal_from_phase0(computed_metrics: Dict[str, Any]) -> float:
        """
        Derive an intelligence signal from Phase 0 computed_metrics.

        The signal is a composite data-quality score:
        - total_records contributes a base (log-scaled, max 1.0 at 100K)
        - field population rate average (0-1)
        - data quality score if available

        Returns a value in [0, 2] where 1.0 = healthy data.
        """
        import math

        total_records = computed_metrics.get("total_records", 0)
        if total_records <= 0:
            return 0.0

        # Log-scaled record count score: 1.0 at 100K, 0.5 at ~316
        record_score = min(1.0, math.log10(max(total_records, 1)) / 5.0)

        # Population rate average across fields
        field_pop = computed_metrics.get("field_population_rates", {})
        if isinstance(field_pop, dict) and field_pop:
            pop_vals = [v for v in field_pop.values() if isinstance(v, (int, float))]
            avg_population = sum(pop_vals) / len(pop_vals) if pop_vals else 0.5
        else:
            avg_population = 0.5

        # Quality score (from data_quality_report if embedded)
        quality = computed_metrics.get("quality_score", avg_population)
        if isinstance(quality, (int, float)):
            quality = float(quality)
        else:
            quality = avg_population

        # Composite: 40% record volume + 30% population + 30% quality
        return (record_score * 0.4) + (avg_population * 0.3) + (quality * 0.3)

    def _infer_goal_completion(self, result: Any) -> bool:
        """
        Infer goal completion from skill result.

        Checks for common success indicators:
        1. Explicit 'success' or 'goal_completed' key
        2. Status field with success value
        3. Non-empty results
        """
        if isinstance(result, dict):
            # Check for explicit success indicators
            if "success" in result:
                return bool(result["success"])
            if "goal_completed" in result:
                return bool(result["goal_completed"])

            # Check status field
            status = result.get("status", "")
            if isinstance(status, str) and status:
                # Only use status if it's non-empty
                return status.lower() in ("success", "completed", "done", "ok")

            # Check for non-empty output
            output = result.get("output")
            if output is not None:
                if isinstance(output, (list, dict)):
                    return len(output) > 0
                return True

            # Check for error
            if "error" in result:
                return result["error"] is None

        # Non-None result is considered successful
        return result is not None

    def get_domain_name(self, skill_name: str) -> str:
        """
        Get domain name string for a skill.

        Convenience method that returns the domain as a string.

        Args:
            skill_name: Name of the skill

        Returns:
            Domain name as string (e.g., "revenue", "content")
        """
        return self.SKILL_DOMAINS.get(skill_name, self.DEFAULT_DOMAIN)

    def list_skills_by_domain(self, domain: str) -> List[str]:
        """
        List all skills in a given domain.

        Args:
            domain: Domain name (e.g., "revenue", "content", "health", "campaign", "generic")

        Returns:
            List of skill names in that domain
        """
        return [
            skill for skill, skill_domain in self.SKILL_DOMAINS.items()
            if skill_domain == domain
        ]

    def consolidate(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Alias for run_consolidation().

        Provides compatibility with code that calls bridge.consolidate().

        Args:
            client_id: Optional client to consolidate. If None, all clients.

        Returns:
            Statistics dict with consolidation metrics
        """
        stats = self.run_consolidation(client_id)
        # Add additional keys expected by callers
        return {
            "patterns_updated": stats.get("patterns_updated", 0),
            "episodes_stored": stats.get("episodes_consolidated", 0),
            **stats
        }

    def consolidate_from_module(
        self,
        module_id: str,
        client_id: str,
        execution_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract learnings from a completed module and store in memory.

        This method is called when a module completes execution. It extracts
        patterns from the module's execution and stores them in the appropriate
        memory layers:
        - Successful skill sequences -> procedural memory
        - Client preferences -> semantic memory
        - Execution episodes -> episodic memory

        Args:
            module_id: The completed module's ID
            client_id: The client/tenant ID
            execution_data: Optional execution state data containing:
                - skill_plan: List of skills executed
                - checkpoints: Execution checkpoints with status/outputs
                - outputs: Module outputs
                - error: Any error that occurred
                - action: Optional action type (e.g., "artifact_uploaded")

        Returns:
            Dict with consolidation statistics:
            - episodes_stored: Number of episodic memories stored
            - patterns_updated: Number of semantic patterns updated
            - procedural_created: Number of procedural entries created
            - promotion_candidates: Number of patterns promoted

        Example:
            >>> bridge.consolidate_from_module(
            ...     module_id="lifecycle-audit-20260130",
            ...     client_id="acme-corp",
            ...     execution_data={
            ...         "skill_plan": ["lifecycle-audit", "cohort-retention"],
            ...         "outputs": {"reports": ["audit.md"]},
            ...         "metadata": {"duration_seconds": 120}
            ...     }
            ... )
        """
        if self.engine is None:
            logger.warning("Intelligence engine not available, skipping consolidation")
            return {
                "episodes_stored": 0,
                "patterns_updated": 0,
                "procedural_created": 0,
                "promotion_candidates": 0,
                "phase0_snapshot_stored": False,
            }

        try:
            # ── Phase 0 snapshot persistence ──────────────────────────────
            # If execution_data contains Phase 0 computed_metrics, store a
            # temporal snapshot in Firebase so we can compute deltas between
            # runs (MoM, WoW, etc.) and feed them to the Predictor.
            phase0_stored = self._store_phase0_snapshot(
                module_id=module_id,
                client_id=client_id,
                execution_data=execution_data,
            )

            # Check if engine has consolidation_manager with the method
            if hasattr(self.engine, 'consolidation_manager') and self.engine.consolidation_manager:
                cm = self.engine.consolidation_manager
                if hasattr(cm, 'consolidate_from_module'):
                    stats = cm.consolidate_from_module(
                        module_id=module_id,
                        client_id=client_id,
                        execution_data=execution_data
                    )
                    stats["phase0_snapshot_stored"] = phase0_stored
                    return stats

            # Fallback: store as episodic memory directly
            logger.info(f"Storing module {module_id} execution as episodic memory")
            
            # Create episode from execution data
            episode_data = {
                "module_id": module_id,
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                **(execution_data or {})
            }
            
            # Store in episodic memory if available
            if hasattr(self.engine, 'episodic_memory') and self.engine.episodic_memory:
                self.engine.episodic_memory.store(
                    tenant_id=client_id,
                    skill_name=execution_data.get("skill_plan", ["unknown"])[0] if execution_data else "module",
                    prediction=None,
                    outcome=episode_data
                )
                return {
                    "episodes_stored": 1,
                    "patterns_updated": 0,
                    "procedural_created": 0,
                    "promotion_candidates": 0,
                    "phase0_snapshot_stored": phase0_stored,
                }

            return {
                "episodes_stored": 0,
                "patterns_updated": 0,
                "procedural_created": 0,
                "promotion_candidates": 0,
                "phase0_snapshot_stored": phase0_stored,
            }

        except Exception as e:
            logger.error(f"Error consolidating from module {module_id}: {e}")
            return {
                "episodes_stored": 0,
                "patterns_updated": 0,
                "procedural_created": 0,
                "promotion_candidates": 0,
                "phase0_snapshot_stored": False,
                "error": str(e)
            }

    def _store_phase0_snapshot(
        self,
        module_id: str,
        client_id: str,
        execution_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store Phase 0 computed_metrics as a temporal snapshot in Firebase.

        Stored at ``system/intelligence/phase0_snapshots/{client_id}/{module_id}/{timestamp}``
        so we can:
        - Compare metrics across runs (MoM/WoW/YoY deltas)
        - Feed historical context to the Predictor
        - Power comparative modules without re-running retrieval

        Also computes a ``_deltas`` dict vs the most recent previous snapshot.
        """
        if not execution_data:
            return False

        # Look for Phase 0 metrics in multiple locations
        phase0_metrics = None
        checkpoints = execution_data.get("checkpoints", [])
        for cp in checkpoints:
            if cp.get("skill_id", "").startswith("platform-retrieval"):
                outputs = cp.get("outputs", {})
                if isinstance(outputs, dict):
                    cm = outputs.get("computed_metrics") or outputs.get("computed_metrics.json")
                    if isinstance(cm, dict):
                        phase0_metrics = cm
                        break
                    elif isinstance(cm, str):
                        import json as _json
                        try:
                            phase0_metrics = _json.loads(cm)
                        except (ValueError, TypeError):
                            pass

        # Also check top-level execution_data
        if not phase0_metrics:
            phase0_metrics = execution_data.get("phase0_computed_metrics")
            if isinstance(phase0_metrics, str):
                import json as _json
                try:
                    phase0_metrics = _json.loads(phase0_metrics)
                except (ValueError, TypeError):
                    phase0_metrics = None

        if not phase0_metrics or not isinstance(phase0_metrics, dict):
            return False

        # Try to store in Firebase
        try:
            fb = None
            if hasattr(self.engine, '_firebase') and self.engine._firebase:
                fb = self.engine._firebase
            elif hasattr(self.engine, 'firebase_client') and self.engine.firebase_client:
                fb = self.engine.firebase_client

            if fb is None:
                logger.debug("No Firebase client available for Phase 0 snapshot")
                return False

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")

            snapshot_doc = {
                "module_id": module_id,
                "client_id": client_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": phase0_metrics,
                "total_records": phase0_metrics.get("total_records", 0),
            }

            # ── Compute deltas vs previous snapshot ───────────────────────
            deltas = self._compute_phase0_deltas(
                fb, client_id, module_id, phase0_metrics
            )
            if deltas:
                snapshot_doc["_deltas"] = deltas

            # Store the snapshot
            collection = f"system/intelligence/phase0_snapshots/{client_id}"
            doc_id = f"{module_id}_{timestamp}"
            fb.set_document(collection, doc_id, snapshot_doc)

            logger.info(
                f"Stored Phase 0 snapshot for {client_id}/{module_id}: "
                f"{phase0_metrics.get('total_records', '?')} records"
                + (f", deltas computed" if deltas else "")
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to store Phase 0 snapshot: {e}")
            return False

    @staticmethod
    def _compute_phase0_deltas(
        fb: Any,
        client_id: str,
        module_id: str,
        current_metrics: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute metric deltas between current and most recent previous snapshot.

        Returns a dict mapping metric_name → {previous, current, delta, pct_change}
        for all numeric top-level metrics, or None if no previous snapshot exists.
        """
        try:
            collection = f"system/intelligence/phase0_snapshots/{client_id}"
            # Query most recent snapshot for this module
            docs = fb.query(
                collection,
                filters=[("module_id", "==", module_id)],
                order_by="timestamp",
                direction="DESCENDING",
                limit=1,
            )
            if not docs:
                return None

            prev_doc = docs[0] if isinstance(docs, list) else docs
            if isinstance(prev_doc, dict):
                prev_metrics = prev_doc.get("metrics", {})
            else:
                prev_metrics = prev_doc.to_dict().get("metrics", {}) if hasattr(prev_doc, "to_dict") else {}

            if not prev_metrics:
                return None

            # Compute deltas for numeric fields
            deltas = {}
            for key, current_val in current_metrics.items():
                if not isinstance(current_val, (int, float)):
                    continue
                prev_val = prev_metrics.get(key)
                if not isinstance(prev_val, (int, float)):
                    continue
                delta = current_val - prev_val
                pct = (delta / prev_val * 100) if prev_val != 0 else 0.0
                deltas[key] = {
                    "previous": prev_val,
                    "current": current_val,
                    "delta": round(delta, 4),
                    "pct_change": round(pct, 2),
                }

            return deltas if deltas else None

        except Exception as e:
            logger.debug(f"Could not compute Phase 0 deltas: {e}")
            return None

    def get_phase0_history(
        self,
        client_id: str,
        module_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical Phase 0 snapshots for a client.

        Used by the Predictor to provide historical context and by
        comparative modules to compute MoM/WoW/YoY trends.

        Args:
            client_id: Client/tenant identifier
            module_id: Optional filter by module
            limit: Max snapshots to return (most recent first)

        Returns:
            List of snapshot dicts with metrics and deltas
        """
        if self.engine is None:
            return []

        try:
            fb = None
            if hasattr(self.engine, '_firebase') and self.engine._firebase:
                fb = self.engine._firebase
            elif hasattr(self.engine, 'firebase_client') and self.engine.firebase_client:
                fb = self.engine.firebase_client

            if fb is None:
                return []

            collection = f"system/intelligence/phase0_snapshots/{client_id}"
            filters = []
            if module_id:
                filters.append(("module_id", "==", module_id))

            docs = fb.query(
                collection,
                filters=filters,
                order_by="timestamp",
                direction="DESCENDING",
                limit=limit,
            )

            results = []
            for doc in (docs or []):
                if isinstance(doc, dict):
                    results.append(doc)
                elif hasattr(doc, "to_dict"):
                    results.append(doc.to_dict())
            return results

        except Exception as e:
            logger.warning(f"Failed to retrieve Phase 0 history: {e}")
            return []

    def get_patterns(self, skill_name: str, client_id: str) -> List[Dict[str, Any]]:
        """
        Get historical patterns for a skill + client combination.

        Used by ContextOrchestrator to load historical execution patterns.

        Args:
            skill_name: Name of the skill
            client_id: Client identifier

        Returns:
            List of pattern dicts
        """
        if self.engine is None:
            return []

        try:
            domain = self.infer_domain(skill_name)
            # Use semantic memory to retrieve patterns
            if hasattr(self.engine, 'semantic_memory') and self.engine.semantic_memory:
                patterns = self.engine.semantic_memory.retrieve_patterns(
                    skill_name=skill_name,
                    domain=domain,
                    tenant_id=client_id,
                    limit=10
                )
                return [p.to_dict() if hasattr(p, 'to_dict') else p for p in patterns]
        except Exception as e:
            logger.warning(f"Failed to get patterns for {skill_name}: {e}")

        return []

    def clear_session(self) -> None:
        """
        Clear working memory and local tracking.

        Call this when starting a new session to reset state.
        """
        self._tracking.clear()

        if self.engine is not None:
            try:
                self.engine.clear_session()
            except Exception as e:
                logger.warning(f"Failed to clear engine session: {e}")

    def __repr__(self) -> str:
        return f"IntelligenceBridge(engine={'loaded' if self._engine else 'not loaded'}, tracking={len(self._tracking)})"


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_bridge: Optional[IntelligenceBridge] = None


def get_bridge() -> IntelligenceBridge:
    """
    Get the default IntelligenceBridge instance.

    Creates a singleton instance on first call.

    Returns:
        IntelligenceBridge instance
    """
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = IntelligenceBridge()
    return _default_bridge


def get_skill_guidance(skill_name: str, client_id: str, inputs: Dict[str, Any] = None) -> SkillGuidance:
    """
    Get guidance for a skill using the default bridge.

    Convenience function that uses the singleton bridge instance.

    Args:
        skill_name: Name of the skill
        client_id: Client/tenant identifier
        inputs: Optional input context

    Returns:
        SkillGuidance with recommended parameters
    """
    return get_bridge().get_skill_guidance(skill_name, client_id, inputs)


def infer_domain(skill_name: str) -> str:
    """
    Get domain name for a skill using the default bridge.

    Convenience function that uses the singleton bridge instance.

    Args:
        skill_name: Name of the skill

    Returns:
        Domain name as string
    """
    return get_bridge().get_domain_name(skill_name)


# =============================================================================
# Unit Tests
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Intelligence Bridge Unit Tests")
    print("=" * 60)

    # Track test results
    tests_passed = 0
    tests_failed = 0

    def test(name: str, condition: bool, details: str = ""):
        global tests_passed, tests_failed
        if condition:
            print(f"  PASS: {name}")
            tests_passed += 1
        else:
            print(f"  FAIL: {name} - {details}")
            tests_failed += 1

    # ==========================================================================
    # Test 1: Domain Inference
    # ==========================================================================
    print("\n--- Test 1: Domain Inference ---")

    bridge = IntelligenceBridge()

    # Test revenue domain skills
    test("lifecycle-audit is revenue", bridge.get_domain_name("lifecycle-audit") == "revenue")
    test("churn-prediction is revenue", bridge.get_domain_name("churn-prediction") == "revenue")
    test("at-risk-detection is revenue", bridge.get_domain_name("at-risk-detection") == "revenue")
    test("deal-velocity is revenue", bridge.get_domain_name("deal-velocity") == "revenue")

    # Test content domain skills
    test("extract-founder-voice is content", bridge.get_domain_name("extract-founder-voice") == "content")
    test("ghostwrite-content is content", bridge.get_domain_name("ghostwrite-content") == "content")
    test("research-company is content", bridge.get_domain_name("research-company") == "content")

    # Test health domain skills
    test("engagement-velocity is health", bridge.get_domain_name("engagement-velocity") == "health")
    test("call-analytics is health", bridge.get_domain_name("call-analytics") == "health")

    # Test campaign domain skills
    test("social-listening-collect is campaign", bridge.get_domain_name("social-listening-collect") == "campaign")
    test("linkedin-keyword-search is campaign", bridge.get_domain_name("linkedin-keyword-search") == "campaign")

    # Test generic domain skills
    test("crm-discovery is generic", bridge.get_domain_name("crm-discovery") == "generic")
    test("skill-builder is generic", bridge.get_domain_name("skill-builder") == "generic")

    # Test unknown skill defaults to content
    test("unknown-skill defaults to content", bridge.get_domain_name("unknown-skill") == "content")

    # ==========================================================================
    # Test 2: List Skills by Domain
    # ==========================================================================
    print("\n--- Test 2: List Skills by Domain ---")

    revenue_skills = bridge.list_skills_by_domain("revenue")
    test("revenue has lifecycle-audit", "lifecycle-audit" in revenue_skills)
    test("revenue has churn-prediction", "churn-prediction" in revenue_skills)
    test("revenue count >= 10", len(revenue_skills) >= 10, f"got {len(revenue_skills)}")

    content_skills = bridge.list_skills_by_domain("content")
    test("content has ghostwrite-content", "ghostwrite-content" in content_skills)
    test("content count >= 10", len(content_skills) >= 10, f"got {len(content_skills)}")

    # ==========================================================================
    # Test 3: All 49 Skills Mapped
    # ==========================================================================
    print("\n--- Test 3: All Skills Mapped ---")

    total_skills = len(IntelligenceBridge.SKILL_DOMAINS)
    test(f"64 skills mapped", total_skills == 64, f"got {total_skills}")

    # Verify domain distribution
    domain_counts = {}
    for skill, domain in IntelligenceBridge.SKILL_DOMAINS.items():
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    print(f"  Domain distribution: {domain_counts}")
    test("revenue domain has skills", domain_counts.get("revenue", 0) > 0)
    test("content domain has skills", domain_counts.get("content", 0) > 0)
    test("health domain has skills", domain_counts.get("health", 0) > 0)
    test("campaign domain has skills", domain_counts.get("campaign", 0) > 0)
    test("generic domain has skills", domain_counts.get("generic", 0) > 0)

    # ==========================================================================
    # Test 4: SkillGuidance Creation
    # ==========================================================================
    print("\n--- Test 4: SkillGuidance Creation ---")

    guidance = bridge.get_skill_guidance("lifecycle-audit", "test-client")
    test("guidance has parameters", isinstance(guidance.parameters, dict))
    test("guidance has confidence", 0 <= guidance.confidence <= 1)
    test("guidance has domain", guidance.domain is not None)
    test("guidance is exploration (no engine)", guidance.is_exploration)
    test("guidance to_dict works", isinstance(guidance.to_dict(), dict))

    # ==========================================================================
    # Test 5: Tracking Workflow
    # ==========================================================================
    print("\n--- Test 5: Tracking Workflow ---")

    # Start tracking
    tracking_id = bridge.start_tracking(
        "lifecycle-audit",
        "test-client",
        guidance,
        expected_signal=50.0,
        expected_baseline=1.0,
        context={"test": True}
    )
    test("tracking_id is string", isinstance(tracking_id, str))
    test("tracking_id has length", len(tracking_id) > 0)

    # Complete tracking
    result = bridge.complete_tracking(
        tracking_id,
        {"output": {"issues": [1, 2, 3, 4, 5]}, "status": "success"},
        metrics={"contacts_processed": 100}
    )
    test("result is LearningResult", isinstance(result, LearningResult))
    test("result has prediction_id", len(result.prediction_id) > 0)
    test("result to_dict works", isinstance(result.to_dict(), dict))

    # ==========================================================================
    # Test 6: Signal Inference
    # ==========================================================================
    print("\n--- Test 6: Signal Inference ---")

    # Test metrics with signal
    signal = bridge._infer_signal({}, {"signal": 42.0})
    test("signal from metrics", signal == 42.0, f"got {signal}")

    # Test metrics with count
    signal = bridge._infer_signal({}, {"count": 100})
    test("signal from count metric", signal == 100.0, f"got {signal}")

    # Test result with list output
    signal = bridge._infer_signal({"output": {"results": [1, 2, 3]}}, {})
    test("signal from list length", signal == 3.0, f"got {signal}")

    # Test numeric result
    signal = bridge._infer_signal(50, {})
    test("signal from numeric result", signal == 50.0, f"got {signal}")

    # Test default
    signal = bridge._infer_signal(None, {})
    test("signal default", signal == 1.0, f"got {signal}")

    # ==========================================================================
    # Test 7: Goal Completion Inference
    # ==========================================================================
    print("\n--- Test 7: Goal Completion Inference ---")

    test("success=True -> completed", bridge._infer_goal_completion({"success": True}))
    test("success=False -> not completed", not bridge._infer_goal_completion({"success": False}))
    test("status=success -> completed", bridge._infer_goal_completion({"status": "success"}))
    test("status=failed -> not completed", not bridge._infer_goal_completion({"status": "failed"}))
    test("non-empty output -> completed", bridge._infer_goal_completion({"output": [1, 2, 3]}))
    test("empty output -> not completed", not bridge._infer_goal_completion({"output": []}))
    test("None -> not completed", not bridge._infer_goal_completion(None))

    # ==========================================================================
    # Test 8: Consolidation (graceful when no engine)
    # ==========================================================================
    print("\n--- Test 8: Consolidation ---")

    stats = bridge.run_consolidation("test-client")
    test("consolidation returns dict", isinstance(stats, dict))
    test("consolidation has expected keys", "episodes_consolidated" in stats)

    # ==========================================================================
    # Test 9: Clear Session
    # ==========================================================================
    print("\n--- Test 9: Clear Session ---")

    bridge._tracking["test"] = {"test": True}
    bridge.clear_session()
    test("tracking cleared", len(bridge._tracking) == 0)

    # ==========================================================================
    # Test 10: Module-level Functions
    # ==========================================================================
    print("\n--- Test 10: Module-level Functions ---")

    default_bridge = get_bridge()
    test("get_bridge returns bridge", isinstance(default_bridge, IntelligenceBridge))

    guidance2 = get_skill_guidance("dormant-detection", "test")
    test("get_skill_guidance works", isinstance(guidance2, SkillGuidance))

    domain = infer_domain("pipeline-analysis")
    test("infer_domain works", domain == "revenue")

    # ==========================================================================
    # Test 11: Domain Enum Integration
    # ==========================================================================
    print("\n--- Test 11: Domain Enum Integration ---")

    try:
        domain_obj = bridge.infer_domain("lifecycle-audit")
        Domain = _get_domain_enum()
        test("infer_domain returns Domain enum", isinstance(domain_obj, Domain))
        test("domain value is revenue", domain_obj.value == "revenue")
    except ImportError:
        print("  SKIP: Domain enum not available (intelligence module not installed)")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 60)
    print(f"Tests passed: {tests_passed}")
    print(f"Tests failed: {tests_failed}")
    print("=" * 60)

    sys.exit(0 if tests_failed == 0 else 1)
