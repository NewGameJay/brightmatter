"""
MH1 Intelligence - Base Domain Adapter

Abstract base class for domain-specific scoring adapters.
Each domain (content, revenue, health, campaign) implements its own
adapter with domain-specific signal interpretation and baseline calculation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScoringResult:
    """
    Result of domain-specific scoring calculation.
    
    Attributes:
        signal: The observed signal strength (domain-specific metric)
        baseline: Expected baseline for comparison
        score: Final computed score (signal / baseline typically)
        context_multiplier: Multiplier applied for contextual factors
        confidence: Confidence in the score [0, 1]
        components: Breakdown of scoring components for explainability
        explanation: Human-readable explanation of the score
        domain: Domain that produced this score
        metadata: Additional domain-specific metadata
    """
    signal: float = 0.0
    baseline: float = 1.0
    score: float = 1.0
    context_multiplier: float = 1.0
    confidence: float = 0.5
    components: Dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    domain: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal": self.signal,
            "baseline": self.baseline,
            "score": self.score,
            "context_multiplier": self.context_multiplier,
            "confidence": self.confidence,
            "components": self.components,
            "explanation": self.explanation,
            "domain": self.domain,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoringResult":
        """Reconstruct from dictionary."""
        return cls(
            signal=data.get("signal", 0.0),
            baseline=data.get("baseline", 1.0),
            score=data.get("score", 1.0),
            context_multiplier=data.get("context_multiplier", 1.0),
            confidence=data.get("confidence", 0.5),
            components=data.get("components", {}),
            explanation=data.get("explanation", ""),
            domain=data.get("domain", ""),
            metadata=data.get("metadata", {}),
        )


class BaseDomainAdapter(ABC):
    """
    Abstract base class for domain-specific scoring adapters.
    
    Each domain adapter transforms raw events into normalized scores
    that can be compared across different contexts. The scoring formula:
    
        score = (signal / baseline) * context_multiplier
    
    Where:
    - signal: Domain-specific metric (e.g., deal velocity, engagement rate)
    - baseline: Expected performance given historical data and context
    - context_multiplier: Adjustments for situational factors
    
    Subclasses must implement:
    - get_domain_name(): Returns the domain identifier
    - get_signal(): Extracts the signal from event data
    - get_baseline(): Calculates expected baseline
    - get_context_multiplier(): Computes situational adjustments
    - validate_event(): Validates event has required fields
    """
    
    @abstractmethod
    def get_domain_name(self) -> str:
        """Return the domain identifier (e.g., 'revenue', 'content')."""
        pass
    
    @abstractmethod
    def get_signal(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Extract the domain-specific signal from an event.
        
        Args:
            event: The raw event data
            context: Additional context (tenant settings, historical data)
            
        Returns:
            The signal value (interpretation is domain-specific)
        """
        pass
    
    @abstractmethod
    def get_baseline(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate the expected baseline for comparison.
        
        Args:
            event: The raw event data
            context: Additional context (tenant settings, historical data)
            
        Returns:
            The baseline value to compare against
        """
        pass
    
    @abstractmethod
    def get_context_multiplier(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Compute situational adjustment factors.
        
        Args:
            event: The raw event data
            context: Additional context (tenant settings, historical data)
            
        Returns:
            Multiplier to apply to the score (typically 0.5 to 2.0)
        """
        pass
    
    @abstractmethod
    def validate_event(self, event: Dict[str, Any]) -> bool:
        """
        Validate that an event has required fields for this domain.
        
        Args:
            event: The raw event data
            
        Returns:
            True if event is valid for this domain
        """
        pass
    
    def _calculate_confidence(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate confidence in the scoring result.
        
        Override in subclasses for domain-specific confidence calculation.
        Default implementation returns 0.5.
        
        Args:
            event: The raw event data
            context: Additional context
            
        Returns:
            Confidence value [0, 1]
        """
        return 0.5
    
    def score(self, event: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ScoringResult:
        """
        Compute the full scoring result for an event.
        
        This is the main entry point for scoring. It orchestrates
        the signal, baseline, and multiplier calculations.
        
        Args:
            event: The raw event data
            context: Optional context (defaults to empty dict)
            
        Returns:
            ScoringResult with all computed values
        """
        context = context or {}
        
        if not self.validate_event(event):
            return ScoringResult(
                signal=0.0,
                baseline=1.0,
                score=0.0,
                confidence=0.0,
                components={"error": "invalid_event"},
                metadata={"domain": self.get_domain_name()},
            )
        
        signal = self.get_signal(event, context)
        baseline = self.get_baseline(event, context)
        multiplier = self.get_context_multiplier(event, context)
        confidence = self._calculate_confidence(event, context)
        
        # Avoid division by zero
        if baseline <= 0:
            baseline = 1.0
        
        raw_score = signal / baseline
        final_score = raw_score * multiplier
        
        explanation = (
            f"Score = (signal {signal:.2f} / baseline {baseline:.2f}) × "
            f"multiplier {multiplier:.2f} = {final_score:.2f}"
        )
        
        return ScoringResult(
            signal=signal,
            baseline=baseline,
            score=final_score,
            context_multiplier=multiplier,
            confidence=confidence,
            components={
                "raw_score": raw_score,
                "multiplier": multiplier,
                "signal": signal,
                "baseline": baseline,
            },
            explanation=explanation,
            domain=self.get_domain_name(),
            metadata={
                "event_type": event.get("type", "unknown"),
            },
        )
    
    def calculate_score(self, event: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ScoringResult:
        """Alias for score() - for compatibility with tests."""
        return self.score(event, context)

    def score_from_phase0_metrics(
        self,
        computed_metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        """
        Score a Phase 0 computed_metrics snapshot using domain-specific logic.

        Phase 0 produces deterministic data (lifecycle distributions, churn
        rates, pipeline metrics, engagement stats) that can be scored by
        domain adapters to produce an intelligence signal *without* any LLM
        involvement.  This enables:

        - Automatic health scoring from CRM data snapshots
        - Revenue scoring from pipeline/deal data
        - Campaign scoring from engagement/delivery metrics
        - Content scoring from audience/channel data

        The default implementation returns a neutral ScoringResult.  Domain
        adapters override this with domain-specific logic.

        Args:
            computed_metrics: Phase 0 computed_metrics.json content
            context: Optional additional context (client config, etc.)

        Returns:
            ScoringResult derived from the Phase 0 data
        """
        return ScoringResult(
            signal=0.0,
            baseline=1.0,
            score=0.0,
            confidence=0.0,
            components={"source": "phase0", "error": "not_implemented"},
            domain=self.get_domain_name(),
            explanation="Phase 0 scoring not implemented for this domain",
        )


__all__ = ["BaseDomainAdapter", "ScoringResult"]
