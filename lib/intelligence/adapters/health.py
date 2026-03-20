"""
Customer Health Domain Adapter for MH1 Intelligence System

This adapter implements customer health scoring and churn risk assessment using
an RFM-inspired (Recency, Frequency, Monetary/Satisfaction) approach adapted
for SaaS customer health metrics.

The health score helps identify:
- At-risk customers requiring proactive intervention
- Healthy customers who may be candidates for expansion
- Patterns in customer behavior that predict churn or renewal

Scoring Formula:
    Signal = recency_score × frequency_score × (0.5 + satisfaction_score)
    Baseline = contract_tier_weight × age_factor × segment_retention_rate
    Context = support_factor × usage_factor × expansion_factor
    
    Final Score = (Signal / Baseline) × Context × Confidence

Risk Levels:
- high_risk: score < 0.3 (immediate intervention needed)
- medium_risk: score < 0.6 (monitor closely, proactive outreach)
- low_risk: score < 0.8 (healthy but room for improvement)
- healthy: score >= 0.8 (strong retention indicators)

The adapter considers multiple signals including:
- Activity recency and frequency
- NPS/satisfaction scores
- Support ticket volume
- Product usage percentile
- Account expansion/contraction signals
- Contract tier and customer tenure
"""

from typing import Any, Dict, Optional

from .base import BaseDomainAdapter, ScoringResult
from ..types import Domain


class HealthAdapter(BaseDomainAdapter):
    """
    Domain adapter for customer health and churn risk scoring.
    
    This adapter transforms customer behavior signals into a health score
    that can be compared across different customer segments and contract tiers.
    
    The scoring approach is inspired by RFM (Recency, Frequency, Monetary) analysis
    commonly used in customer analytics, adapted for SaaS health metrics where
    "Monetary" is replaced with "Satisfaction" signals.
    
    Class Constants:
        RISK_THRESHOLDS: Score thresholds for categorizing customer risk levels
        CONTRACT_TIER_WEIGHTS: Baseline multipliers by contract tier
    
    Example:
        >>> adapter = HealthAdapter()
        >>> event = {
        ...     "days_since_last_activity": 5,
        ...     "activities_per_month": 15,
        ...     "nps_score": 70
        ... }
        >>> context = {
        ...     "contract_tier": "professional",
        ...     "customer_age_months": 18,
        ...     "segment_retention_rate": 0.90
        ... }
        >>> result = adapter.calculate_score(event, context)
        >>> print(f"Health: {result.score:.2f}, Risk: {result.components['risk_level']}")
    """
    
    RISK_THRESHOLDS = {
        "high_risk": 0.3,
        "medium_risk": 0.6,
        "low_risk": 0.8
    }
    
    CONTRACT_TIER_WEIGHTS = {
        "enterprise": 1.5,
        "professional": 1.2,
        "starter": 1.0,
        "free": 0.8,
        "default": 1.0
    }
    
    def get_domain_name(self) -> str:
        """
        Return the domain identifier for health scoring.
        
        Returns:
            String "health" identifying this as the health domain adapter
        """
        return "health"
    
    def get_signal(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate the health signal using RFM-inspired metrics.
        
        Formula: recency_score × frequency_score × (0.5 + satisfaction_score)
        
        The (0.5 + satisfaction) term ensures that even with zero satisfaction,
        recency and frequency still contribute to the signal, while high
        satisfaction can boost the score by up to 50%.
        
        Args:
            event: Event data containing:
                - days_since_last_activity: Days since customer last engaged (default: 30)
                - activities_per_month: Number of activities per month (default: 1)
                - nps_score: Net Promoter Score -100 to 100 (optional)
                - satisfaction_score: Satisfaction score 0-10 (optional, alternative to NPS)
            context: Additional context (not used for signal calculation)
        
        Returns:
            Health signal as a float, typically between 0 and 1.5
            
        Notes:
            - Recency decays linearly over 90 days (1.0 for today, 0.0 for 90+ days)
            - Frequency normalizes to 1.0 at 10+ activities/month
            - Satisfaction normalizes NPS (-100 to 100) or satisfaction (0-10) to 0-1
        """
        # Recency score: 1.0 for today, 0.0 for 90+ days ago
        days_since = event.get("days_since_last_activity", 30)
        recency_score = max(0.0, 1.0 - (days_since / 90.0))
        
        # Frequency score: normalized to 1.0 at 10 activities/month
        activities = event.get("activities_per_month", 1)
        frequency_score = min(activities / 10.0, 1.0)
        
        # Satisfaction score: handle both NPS and satisfaction_score
        if "satisfaction_score" in event:
            # satisfaction_score is on 0-10 scale
            satisfaction_score = event["satisfaction_score"] / 10.0
        elif "nps_score" in event:
            # NPS is on -100 to 100 scale, normalize to 0-1
            nps = event["nps_score"]
            satisfaction_score = (nps + 100) / 200.0
        else:
            # Default to neutral satisfaction (NPS of 50 / 150 ≈ 0.5)
            satisfaction_score = 0.5
        
        # Combine: recency × frequency × (0.5 + satisfaction)
        # The (0.5 + satisfaction) ensures satisfaction boosts but doesn't zero out
        signal = recency_score * frequency_score * (0.5 + satisfaction_score)
        
        return signal
    
    def get_baseline(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate the expected baseline health value.
        
        Formula: contract_tier_weight × age_factor × segment_retention_rate
        
        The baseline represents what we'd expect for a "typical" healthy customer
        in this segment, accounting for:
        - Contract tier (enterprise customers have higher expectations)
        - Customer tenure (longer customers have established patterns)
        - Segment benchmark retention rates
        
        Args:
            event: Event data (not used for baseline calculation)
            context: Context data containing:
                - contract_tier: Customer's contract tier (default: "default")
                - customer_age_months: Months since customer started (default: 12)
                - segment_retention_rate: Expected retention for segment (default: 0.85)
        
        Returns:
            Baseline expectation as a float, typically between 0.5 and 1.5
            
        Notes:
            - Enterprise customers have 1.5x weight (higher expectations)
            - Customer age factor maxes at 1.5x for 24+ month customers
            - Segment retention provides industry/segment benchmark
        """
        # Get contract tier weight
        tier = context.get("contract_tier", "default")
        tier_weight = self.CONTRACT_TIER_WEIGHTS.get(
            tier.lower() if isinstance(tier, str) else tier,
            self.CONTRACT_TIER_WEIGHTS["default"]
        )
        
        # Age factor: longer customers have higher baseline (max 1.5x at 24 months)
        customer_age_months = context.get("customer_age_months", 12)
        age_factor = min(customer_age_months / 24.0, 1.5)
        
        # Segment retention rate as benchmark
        segment_retention = context.get("segment_retention_rate", 0.85)
        
        # Combine factors
        baseline = tier_weight * age_factor * segment_retention
        
        return baseline
    
    def get_context_multiplier(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate context adjustment based on situational factors.
        
        The context multiplier adjusts health scores based on real-time
        indicators that may signal risk or opportunity:
        
        Args:
            event: Event data (not used for context calculation)
            context: Context data containing:
                - open_support_tickets: Number of unresolved tickets (default: 0)
                - product_usage_percentile: Usage rank 0-100 (default: 50)
                - recent_expansion: Whether customer recently expanded (default: False)
                - recent_contraction: Whether customer recently contracted (default: False)
        
        Returns:
            Context multiplier as a float, typically between 0.4 and 1.5
            
        Factor Details:
            - Support tickets: 0 tickets = 1.0, 1-2 = 0.9, 3+ = 0.7
            - Usage percentile: Maps 0-100 to 0.8-1.2 range
            - Recent expansion: 1.2x boost (positive signal)
            - Recent contraction: 0.7x penalty (churn risk signal)
        """
        multiplier = 1.0
        
        # Support ticket factor: more open tickets = lower health
        tickets = context.get("open_support_tickets", 0)
        if tickets == 0:
            ticket_factor = 1.0
        elif tickets <= 2:
            ticket_factor = 0.9
        else:  # 3+ tickets
            ticket_factor = 0.7
        multiplier *= ticket_factor
        
        # Usage percentile factor: 0-100 maps to 0.8-1.2
        # 50th percentile = 1.0, 0th = 0.8, 100th = 1.2
        usage_percentile = context.get("product_usage_percentile", 50)
        usage_factor = 0.8 + (usage_percentile / 100.0) * 0.4
        multiplier *= usage_factor
        
        # Expansion/contraction signals
        if context.get("recent_expansion", False):
            multiplier *= 1.2
        
        if context.get("recent_contraction", False):
            multiplier *= 0.7
        
        return multiplier
    
    def get_risk_level(self, score: float) -> str:
        """
        Categorize a health score into a risk level.
        
        This utility method translates numeric scores into actionable
        risk categories for customer success workflows.
        
        Args:
            score: The calculated health score
        
        Returns:
            Risk level string:
                - "high_risk": score < 0.3 (immediate intervention needed)
                - "medium_risk": score < 0.6 (monitor closely)
                - "low_risk": score < 0.8 (healthy but improvable)
                - "healthy": score >= 0.8 (strong health indicators)
        
        Example:
            >>> adapter = HealthAdapter()
            >>> adapter.get_risk_level(0.25)
            'high_risk'
            >>> adapter.get_risk_level(0.85)
            'healthy'
        """
        if score < self.RISK_THRESHOLDS["high_risk"]:
            return "high_risk"
        elif score < self.RISK_THRESHOLDS["medium_risk"]:
            return "medium_risk"
        elif score < self.RISK_THRESHOLDS["low_risk"]:
            return "low_risk"
        else:
            return "healthy"
    
    def _calculate_confidence(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate confidence in the health score based on data completeness.
        
        Confidence increases as more signals are available. A score calculated
        with only default values has low confidence (0.5), while a score with
        all key metrics has high confidence (0.95).
        
        Args:
            event: Event data to check for available signals
            context: Context data to check for available signals
        
        Returns:
            Confidence value between 0.5 and 0.95
            
        Confidence Breakdown:
            - Base confidence: 0.5
            - NPS or satisfaction_score provided: +0.15
            - activities_per_month provided: +0.10
            - product_usage_percentile provided: +0.10
            - customer_age_months provided: +0.10
            - Maximum confidence: 0.95
        """
        confidence = 0.5
        
        # Satisfaction data provides significant signal
        if "nps_score" in event or "satisfaction_score" in event:
            confidence += 0.15
        
        # Activity data helps assess engagement
        if "activities_per_month" in event:
            confidence += 0.10
        
        # Usage data provides behavioral context
        if "product_usage_percentile" in context:
            confidence += 0.10
        
        # Tenure data helps with baseline accuracy
        if "customer_age_months" in context:
            confidence += 0.10
        
        # Cap at 0.95 (never 100% confident)
        return min(confidence, 0.95)
    
    def validate_event(self, event: Dict[str, Any]) -> bool:
        """
        Validate that an event has data useful for health scoring.
        
        Health scoring can work with minimal data, so we're lenient here.
        We return True if we have any activity or satisfaction signals.
        
        Args:
            event: The raw event data to validate
            
        Returns:
            True if we have any health-relevant data to work with
        """
        # We can score with any of these signals
        health_signals = [
            "days_since_last_activity",
            "activities_per_month",
            "nps_score",
            "satisfaction_score",
        ]
        
        # Return True if we have at least one signal
        return any(key in event for key in health_signals) or len(event) > 0

    def score_from_phase0_metrics(
        self,
        computed_metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        """
        Score customer health from Phase 0 computed_metrics.

        Uses lifecycle distribution, churn/retention rates, and at-risk
        percentages to derive a portfolio-level health score without any
        LLM involvement.

        Signal composition:
        - active_rate (weight 0.35): Higher active rate = healthier portfolio
        - retention_rate (weight 0.30): Higher retention = healthier
        - 1 - at_risk_rate (weight 0.20): Fewer at-risk = healthier
        - field_population quality (weight 0.15): Better data = higher confidence

        Baseline: 0.7 (typical healthy portfolio has ~70% composite health)

        Returns ScoringResult with risk_level in components.
        """
        context = context or {}

        # Extract Phase 0 metrics
        lifecycle_dist = computed_metrics.get("lifecycle_distribution", {})
        active_rate = computed_metrics.get("active_rate", lifecycle_dist.get("active", 0.5))
        retention_rate = computed_metrics.get("retention_rate", 0.85)
        churn_rate = computed_metrics.get("churn_rate", 1.0 - retention_rate)
        at_risk_rate = computed_metrics.get("at_risk_rate", lifecycle_dist.get("at_risk", 0.1))
        dormant_rate = computed_metrics.get("dormant_rate", lifecycle_dist.get("dormant", 0.05))
        total_records = computed_metrics.get("total_records", 0)

        # Ensure rates are floats
        for name in ("active_rate", "retention_rate", "churn_rate", "at_risk_rate", "dormant_rate"):
            val = locals()[name]
            if not isinstance(val, (int, float)):
                locals()[name]  # already handled by defaults above

        # Signal: composite of lifecycle health indicators
        signal = (
            float(active_rate) * 0.35
            + float(retention_rate) * 0.30
            + (1.0 - float(at_risk_rate)) * 0.20
            + (1.0 - float(dormant_rate)) * 0.15
        )

        # Baseline: expected healthy portfolio score
        baseline = 0.70

        # Context multiplier from data quality
        field_pop = computed_metrics.get("field_population_rates", {})
        if isinstance(field_pop, dict) and field_pop:
            pop_vals = [v for v in field_pop.values() if isinstance(v, (int, float))]
            avg_pop = sum(pop_vals) / len(pop_vals) if pop_vals else 0.5
        else:
            avg_pop = 0.5
        # Scale data quality to 0.9-1.1 range
        multiplier = 0.9 + avg_pop * 0.2

        raw_score = signal / baseline if baseline > 0 else signal
        final_score = raw_score * multiplier

        # Confidence based on data volume and completeness
        import math
        volume_conf = min(0.3, math.log10(max(total_records, 1)) / 5.0 * 0.3)
        data_conf = avg_pop * 0.3
        metric_conf = 0.2 if churn_rate != (1.0 - 0.85) else 0.1  # real vs default
        confidence = min(0.95, 0.2 + volume_conf + data_conf + metric_conf)

        risk_level = self.get_risk_level(final_score)

        return ScoringResult(
            signal=signal,
            baseline=baseline,
            score=final_score,
            context_multiplier=multiplier,
            confidence=confidence,
            components={
                "active_rate": float(active_rate),
                "retention_rate": float(retention_rate),
                "churn_rate": float(churn_rate),
                "at_risk_rate": float(at_risk_rate),
                "dormant_rate": float(dormant_rate),
                "risk_level": risk_level,
                "total_records": total_records,
                "data_quality": avg_pop,
                "source": "phase0",
            },
            explanation=(
                f"Phase 0 health: active={active_rate:.0%}, retention={retention_rate:.0%}, "
                f"at_risk={at_risk_rate:.0%} → score={final_score:.2f} ({risk_level})"
            ),
            domain="health",
            metadata={"lifecycle_distribution": lifecycle_dist},
        )

    def calculate_score(self, event: Dict[str, Any], context: Dict[str, Any]) -> ScoringResult:
        """
        Calculate customer health score with risk level categorization.
        
        This method extends the base calculate_score to add risk_level
        to the components dictionary for easy access in downstream workflows.
        
        Args:
            event: Event data containing customer activity signals
            context: Context data containing customer attributes
        
        Returns:
            ScoringResult with additional 'risk_level' in components dict
            
        Example:
            >>> adapter = HealthAdapter()
            >>> event = {"days_since_last_activity": 60, "activities_per_month": 2}
            >>> context = {"contract_tier": "starter", "open_support_tickets": 3}
            >>> result = adapter.calculate_score(event, context)
            >>> print(result.components["risk_level"])
            'high_risk'
        """
        # Get base scoring result using score() method
        result = self.score(event, context)
        
        # Add risk level to components
        result.components["risk_level"] = self.get_risk_level(result.score)
        
        return result
