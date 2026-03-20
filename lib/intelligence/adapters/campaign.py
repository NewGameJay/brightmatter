"""
Campaign Domain Adapter for MH1 Intelligence System

This module implements the campaign-specific scoring adapter for marketing campaign
performance evaluation. It uses the universal scoring formula with campaign-specific
metrics centered around cost efficiency (inverse CPA) and ROI.

Campaign Efficiency Scoring:
---------------------------
The primary signal is cost efficiency, calculated as:
    Signal = conversions / spend * 1000 (inverse CPA, normalized)

This means higher scores indicate better cost efficiency:
- Lower CPA = Higher Signal = Better Performance
- A campaign spending $1000 for 20 conversions ($50 CPA) scores higher than
  one spending $1000 for 10 conversions ($100 CPA)

Baseline Calculation:
--------------------
Baselines are derived from channel-specific target CPAs and seasonal factors:
    Baseline = (1000 / target_cpa) * seasonal_factor

Channel-specific targets reflect industry benchmarks:
- Paid Search: $50 CPA (high intent, higher costs)
- Email: $10 CPA (owned channel, low cost)
- Display: $80 CPA (awareness, higher costs)

Seasonal adjustments account for:
- Q1: Post-holiday slowdown (0.9x)
- Q4: Holiday boost (1.15x)

ROI Calculation:
---------------
ROI is provided as a utility metric:
    ROI = (revenue - spend) / spend

Context Factors:
---------------
Multiple factors adjust the score:
- Funnel stage: Awareness (0.8), Consideration (1.0), Decision (1.3)
- Audience quality: Normalized 0-100 score to 0.8-1.2 multiplier
- Attribution model: First-touch (0.9), Last-touch (1.0), Multi-touch (1.1)
- Campaign maturity: <7 days (0.8), 7-30 days (1.0), 30+ days (1.1)
"""

from datetime import datetime
from typing import Any, Dict, Optional

from .base import BaseDomainAdapter, ScoringResult
from ..types import Domain


class CampaignAdapter(BaseDomainAdapter):
    """
    Domain adapter for marketing campaign performance scoring.
    
    This adapter evaluates campaign efficiency using inverse CPA (cost per acquisition)
    as the primary signal. It supports various marketing channels with channel-specific
    baselines and incorporates seasonal factors, funnel stage, and attribution models.
    
    The scoring philosophy prioritizes cost efficiency:
    - Signal: How efficiently are we acquiring conversions? (1000 / CPA)
    - Baseline: What efficiency should we expect for this channel/season?
    - Context: How do funnel position, audience, and attribution affect expectations?
    
    Example Usage:
        >>> adapter = CampaignAdapter()
        >>> event = {
        ...     "spend": 1000,
        ...     "conversions": 25,
        ...     "channel": "paid_search",
        ...     "revenue": 5000
        ... }
        >>> context = {
        ...     "quarter": "q4",
        ...     "funnel_stage": "decision",
        ...     "attribution_model": "multi_touch"
        ... }
        >>> result = adapter.calculate_score(event, context)
        >>> print(f"Score: {result.score:.2f}, ROI: {adapter.get_roi(event, context):.2%}")
    
    Attributes:
        CHANNEL_ADJUSTMENTS: Channel-specific target CPAs and typical CTRs
        SEASONAL_FACTORS: Quarterly performance adjustment factors
    """
    
    # Channel-specific performance benchmarks
    # target_cpa: Expected cost per acquisition for the channel
    # typical_ctr: Typical click-through rate for budget planning
    CHANNEL_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
        "paid_search": {"target_cpa": 50, "typical_ctr": 0.03},
        "paid_social": {"target_cpa": 40, "typical_ctr": 0.01},
        "display": {"target_cpa": 80, "typical_ctr": 0.005},
        "email": {"target_cpa": 10, "typical_ctr": 0.02},
        "organic_search": {"target_cpa": 0, "typical_ctr": 0.05},
        "referral": {"target_cpa": 20, "typical_ctr": 0.04},
        "default": {"target_cpa": 50, "typical_ctr": 0.02}
    }
    
    # Seasonal performance factors by quarter
    # Adjusts expectations based on typical marketing seasonality
    SEASONAL_FACTORS: Dict[str, float] = {
        "q1": 0.9,   # Post-holiday slowdown
        "q2": 1.0,   # Normal baseline
        "q3": 0.95,  # Summer slowdown
        "q4": 1.15   # Holiday boost
    }
    
    def get_domain_name(self) -> str:
        """
        Return the domain identifier for campaign scoring.
        
        Returns:
            String "campaign" identifying this as the campaign domain adapter.
        """
        return "campaign"
    
    def get_signal(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Extract campaign efficiency signal from event data.
        
        The signal represents cost efficiency using inverse CPA:
            Signal = conversions / spend * 1000
        
        This normalizes efficiency so that:
        - $50 CPA = signal of 20
        - $25 CPA = signal of 40 (better)
        - $100 CPA = signal of 10 (worse)
        
        Special cases:
        - Zero spend with conversions: Returns high score (organic success)
        - No conversions: Falls back to click-based estimation if available
        
        Args:
            event: Campaign event data containing:
                - spend: Total campaign spend (default: 1.0)
                - conversions: Number of conversions (default: 0)
                - clicks: Fallback for conversion estimation
                - conversion_rate: Rate to estimate conversions from clicks
            context: Additional context (not used in signal calculation)
        
        Returns:
            Float signal representing cost efficiency (higher = more efficient)
        
        Example:
            >>> adapter.get_signal({"spend": 500, "conversions": 10}, {})
            20.0  # $50 CPA → 1000/50 = 20
        """
        conversions = event.get("conversions", 0)
        spend = event.get("spend", 1.0)
        
        # Avoid division by zero for spend
        if spend == 0:
            if conversions > 0:
                # Organic success - no spend but got conversions
                # Return a high signal (equivalent to $1 CPA)
                return 1000.0
            # No spend, no conversions - neutral
            return 0.0
        
        # If conversions available, calculate directly
        if conversions > 0:
            cpa = spend / conversions
            return 1000.0 / cpa  # Inverse CPA normalized
        
        # Fallback: estimate conversions from clicks if available
        clicks = event.get("clicks", 0)
        conversion_rate = event.get("conversion_rate", 0.0)
        
        if clicks > 0 and conversion_rate > 0:
            estimated_conversions = clicks * conversion_rate
            if estimated_conversions > 0:
                cpa = spend / estimated_conversions
                return 1000.0 / cpa
        
        # No conversion data available - return spend-normalized signal
        # This penalizes spend without measurable conversions
        return 1000.0 / spend
    
    def get_baseline(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate expected efficiency baseline for this campaign.
        
        The baseline represents expected performance based on:
        1. Channel-specific target CPA
        2. Seasonal adjustment factors
        3. Optional custom target override from context
        
        Formula:
            Baseline = (1000 / target_cpa) * seasonal_factor
        
        Args:
            event: Campaign event data containing:
                - channel: Marketing channel (default: "default")
            context: Additional context containing:
                - target_cpa: Custom CPA target override (optional)
                - quarter: Current quarter for seasonality (e.g., "q1")
        
        Returns:
            Float baseline representing expected efficiency
        
        Example:
            >>> event = {"channel": "email"}
            >>> context = {"quarter": "q4"}
            >>> adapter.get_baseline(event, context)
            115.0  # (1000/10) * 1.15 = 100 * 1.15
        """
        channel = event.get("channel", "default")
        
        # Get channel-specific target CPA
        channel_config = self.CHANNEL_ADJUSTMENTS.get(
            channel, 
            self.CHANNEL_ADJUSTMENTS["default"]
        )
        target_cpa = channel_config["target_cpa"]
        
        # Allow context override for custom targets
        if "target_cpa" in context:
            target_cpa = context["target_cpa"]
        
        # Handle organic channels (no target CPA)
        if target_cpa == 0:
            # For organic, use a very low CPA equivalent as baseline
            target_cpa = 5  # Organic should be very efficient
        
        # Determine quarter for seasonality
        quarter = context.get("quarter")
        if not quarter:
            # Calculate from current date
            current_month = datetime.now().month
            if current_month <= 3:
                quarter = "q1"
            elif current_month <= 6:
                quarter = "q2"
            elif current_month <= 9:
                quarter = "q3"
            else:
                quarter = "q4"
        
        seasonal_factor = self.SEASONAL_FACTORS.get(quarter, 1.0)
        
        # Calculate baseline efficiency
        baseline_efficiency = 1000.0 / target_cpa
        
        return baseline_efficiency * seasonal_factor
    
    def get_context_multiplier(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate context adjustment multiplier for campaign scoring.
        
        Multiple factors combine to adjust expectations:
        
        1. Funnel Stage:
           - awareness: 0.8 (conversions are harder)
           - consideration: 1.0 (baseline)
           - decision: 1.3 (conversions are easier)
        
        2. Audience Quality Score (0-100):
           - Normalized to 0.8-1.2 range
           - Higher quality audiences convert better
        
        3. Attribution Model:
           - first_touch: 0.9 (overcounts early touchpoints)
           - last_touch: 1.0 (baseline)
           - multi_touch: 1.1 (more accurate attribution)
        
        4. Campaign Maturity:
           - <7 days: 0.8 (still in learning phase)
           - 7-30 days: 1.0 (optimized)
           - 30+ days: 1.1 (fully mature)
        
        Args:
            event: Campaign event data (not directly used)
            context: Context containing adjustment factors:
                - funnel_stage: "awareness", "consideration", or "decision"
                - audience_quality_score: 0-100 quality score
                - attribution_model: "first_touch", "last_touch", "multi_touch"
                - campaign_maturity_days: Days campaign has been running
        
        Returns:
            Float multiplier (typically 0.5 to 2.0)
        
        Example:
            >>> context = {
            ...     "funnel_stage": "decision",
            ...     "audience_quality_score": 80,
            ...     "attribution_model": "multi_touch",
            ...     "campaign_maturity_days": 45
            ... }
            >>> adapter.get_context_multiplier({}, context)
            1.69  # 1.3 * 1.12 * 1.1 * 1.1 ≈ 1.69
        """
        multiplier = 1.0
        
        # Funnel stage adjustment
        funnel_stage = context.get("funnel_stage", "consideration")
        funnel_multipliers = {
            "awareness": 0.8,
            "consideration": 1.0,
            "decision": 1.3
        }
        multiplier *= funnel_multipliers.get(funnel_stage, 1.0)
        
        # Audience quality adjustment (0-100 → 0.8-1.2)
        audience_quality = context.get("audience_quality_score")
        if audience_quality is not None:
            # Normalize: 0 → 0.8, 50 → 1.0, 100 → 1.2
            normalized_quality = 0.8 + (audience_quality / 100.0) * 0.4
            multiplier *= normalized_quality
        
        # Attribution model adjustment
        attribution_model = context.get("attribution_model", "last_touch")
        attribution_multipliers = {
            "first_touch": 0.9,
            "last_touch": 1.0,
            "multi_touch": 1.1
        }
        multiplier *= attribution_multipliers.get(attribution_model, 1.0)
        
        # Campaign maturity adjustment
        maturity_days = context.get("campaign_maturity_days")
        if maturity_days is not None:
            if maturity_days < 7:
                multiplier *= 0.8  # Learning phase
            elif maturity_days >= 30:
                multiplier *= 1.1  # Fully mature
            # 7-30 days: no adjustment (1.0)
        
        return multiplier
    
    def _calculate_confidence(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate confidence in the campaign score.
        
        Confidence increases with more data and better measurement:
        - Base confidence: 0.5
        - +0.1 if spend > $100 (meaningful budget)
        - +0.1 if conversions > 5 (statistical significance)
        - +0.1 if campaign running > 7 days (past learning phase)
        - +0.1 if using multi-touch attribution (better accuracy)
        - Maximum: 0.9
        
        Args:
            event: Campaign event data containing spend and conversions
            context: Context containing campaign metadata
        
        Returns:
            Float confidence between 0.5 and 0.9
        
        Example:
            >>> event = {"spend": 500, "conversions": 15}
            >>> context = {"campaign_maturity_days": 14, "attribution_model": "multi_touch"}
            >>> adapter._calculate_confidence(event, context)
            0.9  # 0.5 + 0.1 + 0.1 + 0.1 + 0.1 = 0.9
        """
        confidence = 0.5  # Base confidence
        
        # Meaningful spend increases confidence
        spend = event.get("spend", 0)
        if spend > 100:
            confidence += 0.1
        
        # Statistical significance from conversions
        conversions = event.get("conversions", 0)
        if conversions > 5:
            confidence += 0.1
        
        # Campaign maturity (past learning phase)
        maturity_days = context.get("campaign_maturity_days")
        if maturity_days is not None and maturity_days > 7:
            confidence += 0.1
        
        # Better attribution model
        attribution_model = context.get("attribution_model")
        if attribution_model == "multi_touch":
            confidence += 0.1
        
        # Cap at 0.9 (never fully confident)
        return min(confidence, 0.9)
    
    def get_roi(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate Return on Investment (ROI) for the campaign.
        
        ROI measures the profitability of campaign spend:
            ROI = (revenue - spend) / spend
        
        Interpretation:
        - ROI = 0.0: Break-even (revenue equals spend)
        - ROI = 1.0: 100% return (doubled the investment)
        - ROI = -0.5: Lost 50% of spend
        
        Args:
            event: Campaign event data containing:
                - revenue: Total revenue attributed to campaign
                - spend: Total campaign spend
            context: Additional context (not used)
        
        Returns:
            Float ROI value (can be negative for losses)
        
        Example:
            >>> adapter.get_roi({"spend": 1000, "revenue": 3500}, {})
            2.5  # (3500 - 1000) / 1000 = 250% ROI
        """
        revenue = event.get("revenue", 0)
        spend = event.get("spend", 1)
        
        if spend <= 0:
            if revenue > 0:
                # Pure profit (organic)
                return float('inf')
            return 0.0
        
        return (revenue - spend) / spend
    
    def validate_event(self, event: Dict[str, Any]) -> bool:
        """
        Validate that an event has minimum required fields for scoring.
        
        A campaign event is valid if it contains at least one of:
        - spend: Campaign expenditure
        - conversions: Number of conversions achieved
        - clicks: Click data for estimation
        
        Args:
            event: Campaign event data to validate
        
        Returns:
            True if event has at least one required field
        
        Example:
            >>> adapter.validate_event({"spend": 100})
            True
            >>> adapter.validate_event({"impressions": 1000})
            False
        """
        return (
            "spend" in event or 
            "conversions" in event or 
            "clicks" in event
        )

    def score_from_phase0_metrics(
        self,
        computed_metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        """
        Score campaign performance from Phase 0 computed_metrics.

        Uses engagement data — open rates, click rates, delivery rates,
        campaign counts — to derive a portfolio-level campaign health score.

        Signal composition:
        - open_rate vs benchmark (weight 0.30)
        - click_rate vs benchmark (weight 0.30)
        - engagement_rate (weight 0.25)
        - delivery_quality (weight 0.15)

        Baseline: Expected performance from channel benchmarks.
        """
        import math
        context = context or {}

        open_rate = computed_metrics.get("open_rate", 0.0)
        click_rate = computed_metrics.get("click_rate", 0.0)
        engagement_rate = computed_metrics.get("engagement_rate", 0.0)
        bounce_rate = computed_metrics.get("bounce_rate", 0.0)
        total_campaigns = computed_metrics.get("total_campaigns", 0)
        total_sends = computed_metrics.get("total_sends", 0)
        total_records = computed_metrics.get("total_records", 0)

        # Ensure floats
        open_rate = float(open_rate) if isinstance(open_rate, (int, float)) else 0.0
        click_rate = float(click_rate) if isinstance(click_rate, (int, float)) else 0.0
        engagement_rate = float(engagement_rate) if isinstance(engagement_rate, (int, float)) else 0.0
        bounce_rate = float(bounce_rate) if isinstance(bounce_rate, (int, float)) else 0.0

        # Benchmarks (industry average for email)
        benchmark_open = context.get("benchmark_open_rate", 0.22)
        benchmark_click = context.get("benchmark_click_rate", 0.027)

        # Scores
        open_score = (open_rate / benchmark_open) if benchmark_open > 0 else 0.5
        click_score = (click_rate / benchmark_click) if benchmark_click > 0 else 0.5
        engagement_score = engagement_rate  # 0-1 already
        delivery_score = max(0.0, 1.0 - bounce_rate * 5)  # penalize bounce

        signal = (
            min(open_score, 2.0) * 0.30
            + min(click_score, 2.0) * 0.30
            + engagement_score * 0.25
            + delivery_score * 0.15
        )

        baseline = 1.0

        # Data quality multiplier
        field_pop = computed_metrics.get("field_population_rates", {})
        if isinstance(field_pop, dict) and field_pop:
            pop_vals = [v for v in field_pop.values() if isinstance(v, (int, float))]
            avg_pop = sum(pop_vals) / len(pop_vals) if pop_vals else 0.5
        else:
            avg_pop = 0.5
        multiplier = 0.9 + avg_pop * 0.2

        final_score = (signal / baseline) * multiplier

        # Confidence
        campaign_count = int(total_campaigns) if isinstance(total_campaigns, (int, float)) else 0
        volume_conf = min(0.2, math.log10(max(campaign_count, 1)) / 2.0 * 0.2)
        has_engagement = 0.15 if engagement_rate > 0 else 0.0
        has_delivery = 0.1 if bounce_rate > 0 else 0.0
        confidence = min(0.95, 0.3 + volume_conf + has_engagement + has_delivery + avg_pop * 0.15)

        return ScoringResult(
            signal=signal,
            baseline=baseline,
            score=final_score,
            context_multiplier=multiplier,
            confidence=confidence,
            components={
                "open_rate": open_rate,
                "open_score": open_score,
                "click_rate": click_rate,
                "click_score": click_score,
                "engagement_rate": engagement_rate,
                "bounce_rate": bounce_rate,
                "delivery_score": delivery_score,
                "total_campaigns": campaign_count,
                "source": "phase0",
            },
            explanation=(
                f"Phase 0 campaign: open={open_rate:.1%} (vs {benchmark_open:.1%}), "
                f"click={click_rate:.2%} (vs {benchmark_click:.2%}), "
                f"engagement={engagement_rate:.1%} → score={final_score:.2f}"
            ),
            domain="campaign",
        )
