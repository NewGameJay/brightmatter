"""
MH1 Intelligence Predictor

Implements exploration/exploitation decision making for skill parameter guidance.
Uses semantic patterns and procedural knowledge to make informed predictions,
while maintaining exploration to discover new effective strategies.

The predictor balances:
- Exploitation: Using learned patterns with high confidence
- Exploration: Trying new parameter combinations to discover improvements
"""

import logging
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..types import Domain, SemanticPattern, ProceduralKnowledge

if TYPE_CHECKING:
    from ..memory.semantic import SemanticMemoryStore
    from ..memory.procedural import ProceduralMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class Guidance:
    """
    Output from the predictor providing parameter guidance for skill execution.
    
    Contains recommended parameters, confidence levels, and metadata about
    whether this is an exploration or exploitation decision.
    """
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    uncertainty: float = 0.5
    is_exploration: bool = False
    exploration_reason: str = ""
    patterns_used: List[str] = field(default_factory=list)
    procedural_applied: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": self.parameters,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "is_exploration": self.is_exploration,
            "exploration_reason": self.exploration_reason,
            "patterns_used": self.patterns_used,
            "procedural_applied": self.procedural_applied,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Guidance":
        """Reconstruct Guidance from dictionary."""
        return cls(
            parameters=data.get("parameters", {}),
            confidence=data.get("confidence", 0.5),
            uncertainty=data.get("uncertainty", 0.5),
            is_exploration=data.get("is_exploration", False),
            exploration_reason=data.get("exploration_reason", ""),
            patterns_used=data.get("patterns_used", []),
            procedural_applied=data.get("procedural_applied", []),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class ExplorationConfig:
    """
    Configuration for exploration/exploitation balance.
    
    Attributes:
        base_exploration_rate: Probability of random exploration (default 15%)
        uncertainty_threshold: Explore if best pattern confidence below this (default 0.7)
        novelty_boost: Extra exploration probability for new/unseen skills (default 0.1)
        decay_exploration_with_evidence: Reduce exploration as evidence accumulates
    """
    base_exploration_rate: float = 0.15
    uncertainty_threshold: float = 0.7
    novelty_boost: float = 0.1
    decay_exploration_with_evidence: bool = True


class Predictor:
    """
    Makes exploration/exploitation decisions for skill parameter guidance.
    
    The predictor retrieves learned patterns from semantic memory and
    cross-skill knowledge from procedural memory to generate parameter
    recommendations. It maintains a balance between exploiting known
    good strategies and exploring potentially better alternatives.
    
    Exploration triggers:
    - Random exploration (base_exploration_rate)
    - No patterns available for skill/domain
    - Low confidence in best pattern
    - Novel context not seen before
    """
    
    def __init__(
        self,
        semantic_store: "SemanticMemoryStore",
        procedural_store: "ProceduralMemoryStore",
        config: Optional[ExplorationConfig] = None
    ):
        """
        Initialize the predictor.
        
        Args:
            semantic_store: Store for skill-specific learned patterns
            procedural_store: Store for cross-skill procedural knowledge
            config: Exploration/exploitation configuration
        """
        self._semantic_store = semantic_store
        self._procedural_store = procedural_store
        self._config = config or ExplorationConfig()
    
    def get_guidance(
        self,
        skill_name: str,
        tenant_id: str,
        domain: Domain,
        context: Dict[str, Any]
    ) -> Guidance:
        """
        Main entry point: get parameter guidance for a skill execution.
        
        Retrieves relevant patterns and procedural knowledge, then decides
        whether to explore new parameters or exploit known good ones.
        
        When Phase 0 computed_metrics are present in context (under the key
        ``_phase0_computed_metrics``), the predictor uses real CRM data for
        pattern matching.  For example, if Phase 0 reports churn_rate=0.15,
        the predictor can match patterns that previously produced good
        results at similar churn levels — leading to more accurate guidance
        instead of the default exploration-mode parameters.
        
        Args:
            skill_name: Name of the skill being executed
            tenant_id: Tenant identifier for pattern retrieval
            domain: Business domain for the skill
            context: Current execution context (e.g., customer segment, time of day).
                May contain ``_phase0_computed_metrics`` and ``phase0_*`` keys
                injected by the IntelligenceBridge.
            
        Returns:
            Guidance with recommended parameters and metadata
        """
        logger.debug(f"Getting guidance for {skill_name} in domain {domain.value}")
        
        # Step 1: Retrieve relevant patterns from semantic memory
        patterns = self._retrieve_patterns(skill_name, tenant_id, domain)
        
        # Step 2: Get procedural knowledge for this skill/domain
        procedural = self._retrieve_procedural(skill_name, domain)
        
        # Step 2.5: If Phase 0 data is available, adjust default parameters
        # to reflect actual data state (e.g., set segment_count based on
        # actual lifecycle distribution, thresholds based on real churn rate).
        phase0_adjustments = self._phase0_parameter_adjustments(
            skill_name, domain, context
        )
        
        # Step 3: Decide explore or exploit
        should_explore, reason = self._should_explore(patterns, context)
        
        # Step 4: Generate guidance
        if should_explore or not patterns:
            guidance = self._explore(skill_name, domain, context, procedural, reason)
        else:
            guidance = self._exploit(patterns, procedural, context)
        
        # Step 5: Apply Phase 0 adjustments on top of guidance
        if phase0_adjustments:
            for key, value in phase0_adjustments.items():
                if key not in guidance.parameters:
                    guidance.parameters[key] = value
            # Phase 0 data increases confidence since we have real data
            guidance.confidence = min(1.0, guidance.confidence + 0.1)
            guidance.uncertainty = max(0.0, guidance.uncertainty - 0.1)

        # Step 6: Incorporate upstream strategy context
        # When upstream strategy skills have completed (e.g., positioning-angles
        # before email-sequences), their outputs inform this skill's parameters.
        # This closes the feedback loop: strategy → execution → learning.
        upstream = context.get("_upstream_strategy")
        if isinstance(upstream, dict) and upstream:
            strategy_adjustments = self._upstream_strategy_adjustments(
                skill_name, domain, upstream
            )
            if strategy_adjustments:
                for key, value in strategy_adjustments.items():
                    if key not in guidance.parameters:
                        guidance.parameters[key] = value
                guidance.confidence = min(1.0, guidance.confidence + 0.05)
                guidance.uncertainty = max(0.0, guidance.uncertainty - 0.05)

        return guidance
    
    def _retrieve_patterns(
        self,
        skill_name: str,
        tenant_id: str,
        domain: Domain
    ) -> List[SemanticPattern]:
        """Retrieve relevant semantic patterns for the skill."""
        try:
            return self._semantic_store.retrieve_patterns(
                skill_name=skill_name,
                domain=domain,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.warning(f"Failed to retrieve patterns: {e}")
        return []
    
    def _retrieve_procedural(
        self,
        skill_name: str,
        domain: Domain
    ) -> List[ProceduralKnowledge]:
        """Retrieve applicable procedural knowledge."""
        try:
            if hasattr(self._procedural_store, "get_applicable"):
                return self._procedural_store.get_applicable(
                    skill_name=skill_name,
                    domain=domain.value
                )
            elif hasattr(self._procedural_store, "retrieve"):
                return self._procedural_store.retrieve(
                    skill_name=skill_name,
                    domain=domain
                )
        except Exception as e:
            logger.warning(f"Failed to retrieve procedural knowledge: {e}")
        return []
    
    def _should_explore(
        self,
        patterns: List[SemanticPattern],
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Decide whether to explore or exploit.
        
        Returns (should_explore, reason) based on:
        1. Random exploration: random.random() < base_exploration_rate
        2. No patterns available
        3. Best pattern confidence < uncertainty_threshold
        4. No patterns match current context
        
        Args:
            patterns: Available semantic patterns
            context: Current execution context
            
        Returns:
            Tuple of (should_explore, reason_string)
        """
        # Check 1: Random exploration
        if random.random() < self._config.base_exploration_rate:
            return (True, "random_exploration")
        
        # Check 2: No patterns available
        if not patterns:
            return (True, "no_patterns_available")
        
        # Check 3: Best pattern confidence below threshold
        best_pattern = max(patterns, key=lambda p: p.confidence * p.recent_accuracy)
        if best_pattern.confidence < self._config.uncertainty_threshold:
            return (True, f"low_confidence_{best_pattern.confidence:.2f}")
        
        # Check 4: No patterns match the current context
        matching_patterns = [
            p for p in patterns
            if self._context_matches(p.condition, context)
        ]
        if not matching_patterns:
            return (True, "novel_context")
        
        # Exploit: use learned patterns
        return (False, "")
    
    def _explore(
        self,
        skill_name: str,
        domain: Domain,
        context: Dict[str, Any],
        procedural: List[ProceduralKnowledge],
        reason: str
    ) -> Guidance:
        """
        Generate exploratory guidance with perturbed parameters.
        
        When exploring, we:
        1. Start with default parameters for the skill/domain
        2. Apply any applicable procedural knowledge
        3. Perturb parameters to try new values
        
        Args:
            skill_name: Name of the skill
            domain: Business domain
            context: Current execution context
            procedural: Applicable procedural knowledge
            reason: Why we're exploring
            
        Returns:
            Guidance with exploration flag set
        """
        logger.debug(f"Exploring for {skill_name}: {reason}")
        
        # Step 1: Get default parameters
        parameters = self._get_default_parameters(skill_name, domain)
        
        # Step 2: Apply procedural knowledge
        procedural_applied = []
        for knowledge in procedural:
            parameters = self._apply_procedural(parameters, knowledge)
            procedural_applied.append(knowledge.knowledge_id)
        
        # Step 3: Perturb for exploration
        parameters = self._perturb_parameters(parameters)
        
        return Guidance(
            parameters=parameters,
            confidence=0.3,
            uncertainty=0.7,
            is_exploration=True,
            exploration_reason=reason,
            patterns_used=[],
            procedural_applied=procedural_applied,
        )
    
    def _exploit(
        self,
        patterns: List[SemanticPattern],
        procedural: List[ProceduralKnowledge],
        context: Dict[str, Any]
    ) -> Guidance:
        """
        Generate guidance by exploiting learned patterns.
        
        When exploiting, we:
        1. Filter patterns to those matching current context
        2. Select the best pattern by confidence × recent_accuracy
        3. Build parameters from the pattern's recommendation
        4. Apply procedural knowledge for cross-skill insights
        5. Calculate combined confidence
        
        Args:
            patterns: Available semantic patterns
            procedural: Applicable procedural knowledge
            context: Current execution context
            
        Returns:
            Guidance with exploitation parameters
        """
        # Step 1: Filter patterns matching context
        matching_patterns = [
            p for p in patterns
            if self._context_matches(p.condition, context)
        ]
        
        # Fall back to all patterns if none match exactly
        if not matching_patterns:
            matching_patterns = patterns
        
        # Step 2: Select best pattern by confidence × recent_accuracy
        best_pattern = max(
            matching_patterns,
            key=lambda p: p.confidence * p.recent_accuracy
        )
        
        # Step 3: Build parameters from recommendation
        parameters = dict(best_pattern.recommendation)
        patterns_used = [best_pattern.pattern_id]
        
        # Step 4: Apply procedural knowledge
        procedural_applied = []
        for knowledge in procedural:
            parameters = self._apply_procedural(parameters, knowledge)
            procedural_applied.append(knowledge.knowledge_id)
        
        # Step 5: Calculate combined confidence
        pattern_confidence = best_pattern.confidence * best_pattern.recent_accuracy
        
        if procedural and procedural_applied:
            # Average pattern confidence with procedural confidence
            procedural_confidences = [
                k.cross_skill_confidence
                for k in procedural
                if k.knowledge_id in procedural_applied
            ]
            if procedural_confidences:
                avg_procedural = sum(procedural_confidences) / len(procedural_confidences)
                combined_confidence = (pattern_confidence + avg_procedural) / 2
            else:
                combined_confidence = pattern_confidence
        else:
            combined_confidence = pattern_confidence
        
        # Clamp confidence to [0, 1]
        combined_confidence = max(0.0, min(1.0, combined_confidence))
        
        logger.debug(
            f"Exploiting pattern {best_pattern.pattern_id} "
            f"with confidence {combined_confidence:.2f}"
        )
        
        return Guidance(
            parameters=parameters,
            confidence=combined_confidence,
            uncertainty=1.0 - combined_confidence,
            is_exploration=False,
            exploration_reason="",
            patterns_used=patterns_used,
            procedural_applied=procedural_applied,
        )
    
    def _phase0_parameter_adjustments(
        self,
        skill_name: str,
        domain: Domain,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Derive parameter adjustments from Phase 0 computed_metrics.

        When Phase 0 retrieval has run, the context contains real CRM data
        under ``_phase0_computed_metrics``.  This method translates that
        data into concrete parameter recommendations:

        - **Health domain**: Uses lifecycle distribution to set segment counts,
          churn rate to set alert thresholds, at-risk percentage to set
          engagement thresholds.
        - **Revenue domain**: Uses pipeline metrics for velocity expectations,
          deal counts for batch sizing.
        - **Campaign domain**: Uses engagement rates for baseline expectations.
        - **Content domain**: Uses audience metrics for targeting parameters.

        Returns an empty dict if no Phase 0 data is available.
        """
        cm = context.get("_phase0_computed_metrics")
        if not cm or not isinstance(cm, dict):
            return {}

        adjustments: Dict[str, Any] = {}

        # ── Universal adjustments ─────────────────────────────────────
        total_records = cm.get("total_records", 0)
        if total_records > 0:
            adjustments["data_record_count"] = total_records
            # Suggest batch size based on data volume
            if total_records > 100000:
                adjustments["batch_size"] = 10000
            elif total_records > 10000:
                adjustments["batch_size"] = 1000

        # ── Domain-specific adjustments ───────────────────────────────
        if domain == Domain.HEALTH:
            churn_rate = cm.get("churn_rate")
            if isinstance(churn_rate, (int, float)):
                # More aggressive threshold when churn is high
                adjustments["alert_threshold"] = max(0.2, min(0.5, churn_rate * 1.5))
                adjustments["focus_retention"] = churn_rate > 0.10

            at_risk_rate = cm.get("at_risk_rate")
            if isinstance(at_risk_rate, (int, float)):
                adjustments["engagement_threshold"] = max(0.05, at_risk_rate * 0.8)

            # Use lifecycle distribution to inform segment count
            lifecycle_dist = cm.get("lifecycle_distribution", {})
            if isinstance(lifecycle_dist, dict) and lifecycle_dist:
                non_trivial = sum(1 for v in lifecycle_dist.values()
                                 if isinstance(v, (int, float)) and v > 0.02)
                adjustments["segment_count"] = max(3, min(8, non_trivial + 1))

        elif domain == Domain.REVENUE:
            avg_deal = cm.get("avg_deal_size")
            if isinstance(avg_deal, (int, float)) and avg_deal > 0:
                adjustments["avg_deal_size_observed"] = avg_deal
                adjustments["include_revenue_impact"] = True

            pipeline_velocity = cm.get("pipeline_velocity")
            if isinstance(pipeline_velocity, (int, float)):
                adjustments["expected_velocity"] = pipeline_velocity

            conversion_rate = cm.get("conversion_rate")
            if isinstance(conversion_rate, (int, float)):
                adjustments["conversion_baseline"] = conversion_rate

        elif domain == Domain.CAMPAIGN:
            open_rate = cm.get("open_rate")
            if isinstance(open_rate, (int, float)):
                adjustments["expected_open_rate"] = open_rate

            click_rate = cm.get("click_rate")
            if isinstance(click_rate, (int, float)):
                adjustments["expected_click_rate"] = click_rate

            engagement_rate = cm.get("engagement_rate")
            if isinstance(engagement_rate, (int, float)):
                adjustments["engagement_baseline"] = engagement_rate

        elif domain == Domain.CONTENT:
            # Content skills benefit from knowing audience size
            audience_size = cm.get("total_contacts") or cm.get("total_records")
            if isinstance(audience_size, (int, float)) and audience_size > 0:
                adjustments["audience_size"] = int(audience_size)

        return adjustments

    def _upstream_strategy_adjustments(
        self,
        skill_name: str,
        domain: Domain,
        upstream: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Derive parameter adjustments from upstream strategy skill outputs.

        When strategy skills (e.g., positioning-angles, lifecycle-audit)
        complete before execution skills (e.g., email-sequences, direct-
        response-copy), their outputs carry recommendations that should
        inform downstream parameter choices.

        This closes the feedback loop: the Predictor records which upstream
        strategy context led to good downstream outcomes, so over time it
        learns to recommend parameters that align with effective strategies.

        Args:
            skill_name: The current skill being guided
            domain: Business domain for the skill
            upstream: Dict mapping dep_node_id → {skill_id, metrics, summary}

        Returns:
            Dict of parameter adjustments (may be empty)
        """
        adjustments: Dict[str, Any] = {}

        # Collect upstream skill IDs for pattern context
        upstream_skills = [
            info.get("skill_id", "")
            for info in upstream.values()
            if isinstance(info, dict)
        ]
        if upstream_skills:
            adjustments["upstream_skills"] = upstream_skills

        # Propagate numeric metrics from upstream strategy nodes
        for _dep_id, info in upstream.items():
            if not isinstance(info, dict):
                continue
            dep_skill = info.get("skill_id", "")
            dep_metrics = info.get("metrics", {})

            if not isinstance(dep_metrics, dict):
                continue

            # Forward strategy-produced metrics with namespaced keys
            # so the learning loop can correlate them with outcomes
            for key, val in dep_metrics.items():
                if isinstance(val, (int, float)):
                    adjustments[f"upstream_{dep_skill}_{key}"] = val

        return adjustments

    def _context_matches(
        self,
        pattern_ctx: Dict[str, Any],
        current_ctx: Dict[str, Any]
    ) -> bool:
        """
        Check if pattern condition matches current context.
        
        For numeric values: allows 30% tolerance
        For other values: requires exact match
        
        Args:
            pattern_ctx: Pattern's condition dictionary
            current_ctx: Current execution context
            
        Returns:
            True if contexts match within tolerance
        """
        if not pattern_ctx:
            # Empty pattern condition matches everything
            return True
        
        for key, pattern_value in pattern_ctx.items():
            if key not in current_ctx:
                # Context missing required key
                return False
            
            current_value = current_ctx[key]
            
            # Numeric comparison with 30% tolerance
            if isinstance(pattern_value, (int, float)) and isinstance(current_value, (int, float)):
                if pattern_value == 0:
                    # Avoid division by zero; require exact match for zero
                    if current_value != 0:
                        return False
                else:
                    tolerance = abs(pattern_value) * 0.3
                    if abs(current_value - pattern_value) > tolerance:
                        return False
            else:
                # Exact match for non-numeric values
                if current_value != pattern_value:
                    return False
        
        return True
    
    def _get_default_parameters(
        self,
        skill_name: str,
        domain: Domain
    ) -> Dict[str, Any]:
        """
        Get sensible default parameters for known skills.
        
        Provides reasonable starting points for exploration when
        no learned patterns exist.
        
        Args:
            skill_name: Name of the skill
            domain: Business domain
            
        Returns:
            Dictionary of default parameters
        """
        # Skill-specific defaults
        skill_defaults = {
            "dormant-detection": {
                "inactivity_days": 90,
                "engagement_threshold": 0.1,
                "lookback_window_days": 180,
                "min_previous_activity": 3,
                "include_partial_churn": True,
            },
            "lifecycle-audit": {
                "segment_count": 5,
                "min_segment_size": 100,
                "analyze_transitions": True,
                "cohort_period_days": 30,
                "include_revenue_impact": True,
            },
            "content-strategy": {
                "topics_per_pillar": 5,
                "content_depth": "comprehensive",
                "keyword_density": 0.02,
                "min_word_count": 1500,
                "include_cta": True,
            },
            "email-campaign": {
                "send_hour": 10,
                "send_day": "tuesday",
                "subject_length": 50,
                "personalization_level": "medium",
                "ab_test_split": 0.1,
            },
            "lead-scoring": {
                "score_range_max": 100,
                "decay_rate_per_day": 0.02,
                "activity_weight": 0.4,
                "demographic_weight": 0.3,
                "behavioral_weight": 0.3,
            },
        }
        
        # Domain-specific adjustments
        domain_adjustments = {
            Domain.REVENUE: {
                "include_revenue_impact": True,
                "prioritize_high_value": True,
            },
            Domain.HEALTH: {
                "focus_retention": True,
                "alert_threshold": 0.3,
            },
            Domain.CONTENT: {
                "engagement_focus": True,
                "virality_weight": 0.2,
            },
            Domain.CAMPAIGN: {
                "track_attribution": True,
                "roi_threshold": 1.5,
            },
        }
        
        # Start with skill defaults or empty dict
        params = dict(skill_defaults.get(skill_name, {}))
        
        # Apply domain adjustments
        if domain in domain_adjustments:
            params.update(domain_adjustments[domain])
        
        # If no skill-specific defaults, provide generic parameters
        if not params:
            params = {
                "threshold": 0.5,
                "window_days": 30,
                "limit": 100,
                "include_metadata": True,
            }
        
        return params
    
    def _apply_procedural(
        self,
        parameters: Dict[str, Any],
        knowledge: ProceduralKnowledge
    ) -> Dict[str, Any]:
        """
        Blend procedural knowledge into parameters.
        
        For numeric parameters: 70% existing + 30% procedural
        For non-numeric: procedural overrides if present
        
        Args:
            parameters: Current parameter dictionary
            knowledge: Procedural knowledge to apply
            
        Returns:
            Updated parameters dictionary
        """
        if not knowledge.knowledge:
            return parameters
        
        result = dict(parameters)
        
        for key, procedural_value in knowledge.knowledge.items():
            if key in result:
                existing_value = result[key]
                
                # Numeric blending: 70% existing + 30% procedural
                if isinstance(existing_value, (int, float)) and isinstance(procedural_value, (int, float)):
                    blended = existing_value * 0.7 + procedural_value * 0.3
                    # Preserve int type if both were ints
                    if isinstance(existing_value, int) and isinstance(procedural_value, int):
                        result[key] = int(round(blended))
                    else:
                        result[key] = blended
                else:
                    # Non-numeric: keep existing (procedural doesn't override)
                    pass
            else:
                # New key from procedural: add it
                result[key] = procedural_value
        
        return result
    
    def _perturb_parameters(
        self,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add ±20% noise to numeric parameters for exploration.
        
        This helps discover potentially better parameter values
        by trying variations around the current settings.
        
        Args:
            parameters: Current parameter dictionary
            
        Returns:
            Perturbed parameters dictionary
        """
        result = dict(parameters)
        perturbation_range = 0.2  # ±20%
        
        for key, value in result.items():
            if isinstance(value, (int, float)):
                # Calculate perturbation
                perturbation = value * random.uniform(-perturbation_range, perturbation_range)
                perturbed = value + perturbation
                
                # Preserve int type
                if isinstance(value, int):
                    result[key] = int(round(perturbed))
                else:
                    result[key] = perturbed
                
                # Ensure non-negative for typical parameters
                if result[key] < 0 and value >= 0:
                    result[key] = 0 if isinstance(value, int) else 0.0
        
        return result


__all__ = [
    "ExplorationConfig",
    "Guidance",
    "Predictor",
]
