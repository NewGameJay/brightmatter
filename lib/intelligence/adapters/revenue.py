"""
MH1 Intelligence - Revenue Domain Adapter

Adapter for revenue/deal scoring focused on pipeline velocity and deal progression.

Pipeline Velocity Scoring:
    The revenue adapter measures how quickly deals move through the sales pipeline
    compared to segment-specific benchmarks. A deal that progresses faster than
    expected receives a higher signal score.
    
    velocity_score = expected_days / actual_days
    
    - velocity_score > 1.0: Deal is moving faster than expected (good)
    - velocity_score = 1.0: Deal is on track
    - velocity_score < 1.0: Deal is moving slower than expected (needs attention)

Deal Progression:
    The adapter tracks deals through standard B2B stages:
    1. Lead → MQL (Marketing Qualified Lead)
    2. MQL → SQL (Sales Qualified Lead)
    3. SQL → Opportunity
    4. Opportunity → Close (Won or Lost)
    
    Each segment (enterprise, mid-market, SMB) has different expected timelines.

Context Factors:
    - Deal size relative to segment average
    - Strategic account designation
    - Competition level in the deal
    - Historical win rates for the segment
"""

from typing import Any, Dict, Optional

from .base import BaseDomainAdapter, ScoringResult
from ..types import Domain


class RevenueAdapter(BaseDomainAdapter):
    """
    Domain adapter for revenue and deal scoring.
    
    Specializes in:
    - Pipeline velocity (time between stages vs benchmarks)
    - Deal value assessment
    - Win probability adjustments
    - Segment-specific scoring
    """
    
    # Segment benchmarks: days expected for each stage transition
    SEGMENT_BENCHMARKS = {
        "enterprise": {
            "lead_to_mql": 14,
            "mql_to_sql": 21,
            "sql_to_opportunity": 30,
            "opportunity_to_close": 60,
            "avg_deal_size": 100000,
            "typical_win_rate": 0.25,
        },
        "mid_market": {
            "lead_to_mql": 7,
            "mql_to_sql": 14,
            "sql_to_opportunity": 21,
            "opportunity_to_close": 30,
            "avg_deal_size": 25000,
            "typical_win_rate": 0.30,
        },
        "smb": {
            "lead_to_mql": 3,
            "mql_to_sql": 7,
            "sql_to_opportunity": 14,
            "opportunity_to_close": 14,
            "avg_deal_size": 5000,
            "typical_win_rate": 0.35,
        },
        "default": {
            "lead_to_mql": 7,
            "mql_to_sql": 14,
            "sql_to_opportunity": 21,
            "opportunity_to_close": 30,
            "avg_deal_size": 20000,
            "typical_win_rate": 0.30,
        },
    }
    
    # Stage transition mapping for benchmark lookup
    STAGE_TRANSITIONS = {
        ("lead", "mql"): "lead_to_mql",
        ("mql", "sql"): "mql_to_sql",
        ("sql", "opportunity"): "sql_to_opportunity",
        ("opportunity", "closed"): "opportunity_to_close",
        ("opportunity", "won"): "opportunity_to_close",
        ("opportunity", "lost"): "opportunity_to_close",
    }
    
    def get_domain_name(self) -> str:
        """Return the domain identifier."""
        return "revenue"
    
    def get_signal(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate pipeline velocity score.
        
        Formula: expected_days / actual_days
        
        A higher score means the deal is moving faster than expected.
        Also incorporates deal value bonus for closed deals.
        
        Args:
            event: Event with current_stage, previous_stage, actual_days
            context: Context with segment information
            
        Returns:
            Velocity score (>1.0 = faster than expected)
        """
        current_stage = event.get("current_stage", "").lower()
        previous_stage = event.get("previous_stage", "").lower()
        actual_days = event.get("actual_days", 0)
        
        # Get segment benchmarks
        segment = context.get("segment", "default")
        benchmarks = self.SEGMENT_BENCHMARKS.get(segment, self.SEGMENT_BENCHMARKS["default"])
        
        # Handle closed deals: add value bonus
        if current_stage in ("won", "closed_won"):
            deal_value = event.get("deal_value", 0)
            avg_deal_size = benchmarks["avg_deal_size"]
            
            # Base velocity score for close
            velocity_score = self._get_velocity_score(
                previous_stage, "closed", actual_days, benchmarks
            )
            
            # Value bonus: deals larger than average get a boost
            if deal_value > 0 and avg_deal_size > 0:
                value_ratio = deal_value / avg_deal_size
                # Cap the bonus at 2x to avoid outliers dominating
                value_bonus = min(value_ratio, 2.0)
                velocity_score *= (1 + (value_bonus - 1) * 0.5)  # Dampened bonus
            
            return velocity_score
        
        # Standard stage progression
        return self._get_velocity_score(
            previous_stage, current_stage, actual_days, benchmarks
        )
    
    def _get_velocity_score(
        self,
        from_stage: str,
        to_stage: str,
        actual_days: float,
        benchmarks: Dict[str, Any],
    ) -> float:
        """
        Calculate velocity score for a stage transition.
        
        Args:
            from_stage: Previous stage
            to_stage: Current stage
            actual_days: Days spent in transition
            benchmarks: Segment benchmarks
            
        Returns:
            Velocity score
        """
        # Look up the transition
        transition_key = (from_stage, to_stage)
        benchmark_key = self.STAGE_TRANSITIONS.get(transition_key)
        
        if not benchmark_key:
            # Try to infer from current stage if previous unknown
            for (from_s, to_s), key in self.STAGE_TRANSITIONS.items():
                if to_s == to_stage:
                    benchmark_key = key
                    break
        
        if not benchmark_key:
            # No matching transition, return neutral score
            return 1.0
        
        expected_days = benchmarks.get(benchmark_key, 14)  # Default 14 days
        
        if actual_days <= 0:
            return 1.0  # No time data, return neutral
        
        return expected_days / actual_days
    
    def get_baseline(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate expected baseline using segment benchmarks and historical data.
        
        Formula: segment_benchmark * historical_multiplier
        
        The baseline represents the expected performance level.
        
        Args:
            event: The deal event
            context: Context with segment and historical_win_rate
            
        Returns:
            Normalized baseline (typically around 1.0)
        """
        segment = context.get("segment", "default")
        benchmarks = self.SEGMENT_BENCHMARKS.get(segment, self.SEGMENT_BENCHMARKS["default"])
        
        typical_win_rate = benchmarks["typical_win_rate"]
        historical_win_rate = context.get("historical_win_rate", typical_win_rate)
        
        # Calculate multiplier based on historical performance
        # If historical win rate is higher than typical, baseline expectation is higher
        if typical_win_rate > 0:
            multiplier = historical_win_rate / typical_win_rate
        else:
            multiplier = 1.0
        
        # Normalized baseline (1.0 represents on-track performance)
        return 1.0 * multiplier
    
    def get_context_multiplier(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate context-based scoring adjustment.
        
        Considers:
        - Deal size vs segment average (larger deals = higher priority)
        - Strategic account designation
        - Competition level
        
        Args:
            event: The deal event with deal_value
            context: Context with is_strategic, competition_level
            
        Returns:
            Multiplier to apply to score
        """
        multiplier = 1.0
        
        # Get segment benchmarks
        segment = context.get("segment", "default")
        benchmarks = self.SEGMENT_BENCHMARKS.get(segment, self.SEGMENT_BENCHMARKS["default"])
        
        # Deal size factor
        deal_value = event.get("deal_value", 0)
        avg_deal_size = benchmarks["avg_deal_size"]
        
        if deal_value > 0 and avg_deal_size > 0:
            size_ratio = deal_value / avg_deal_size
            # Scale: 0.5x for tiny deals, up to 1.5x for deals 3x average
            # Capped to avoid outliers
            size_multiplier = 0.5 + min(size_ratio, 3.0) * (1.0 / 3.0)
            multiplier *= size_multiplier
        
        # Strategic account bonus
        if context.get("is_strategic", False):
            multiplier *= 1.5
        
        # Competition level adjustment
        competition_level = context.get("competition_level", "medium").lower()
        competition_factors = {
            "high": 0.8,    # Harder to win, dampen expectations
            "medium": 1.0,  # Normal
            "low": 1.2,     # Easier to win, boost score
            "none": 1.3,    # No competition, significant boost
        }
        multiplier *= competition_factors.get(competition_level, 1.0)
        
        return multiplier
    
    def _calculate_confidence(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate confidence in the revenue scoring result.
        
        Revenue scoring has more uncertainty than content scoring because
        deal outcomes depend on many external factors (buyer decisions,
        budget cycles, competitive dynamics).
        
        Confidence factors:
        - Base: 0.6 (lower than content due to inherent uncertainty)
        - +0.1 if deal_size known
        - +0.1 if historical_win_rate provided
        - +0.1 if stage progression is clear (both current and previous known)
        
        Args:
            event: The deal event
            context: Context with historical data
            
        Returns:
            Confidence value [0, 0.95]
        """
        confidence = 0.6  # Base confidence for revenue domain
        
        # Deal size known
        if event.get("deal_value", 0) > 0:
            confidence += 0.1
        
        # Historical win rate provided
        if "historical_win_rate" in context:
            confidence += 0.1
        
        # Clear stage progression (both stages known)
        has_current = bool(event.get("current_stage"))
        has_previous = bool(event.get("previous_stage"))
        if has_current and has_previous:
            confidence += 0.1
        
        # Cap at 0.95 to maintain appropriate uncertainty
        return min(confidence, 0.95)
    
    def validate_event(self, event: Dict[str, Any]) -> bool:
        """
        Validate that an event is suitable for revenue scoring.
        
        An event is valid if it has either:
        - current_stage: Indicates a stage in the pipeline
        - deal_value: Indicates a monetary value
        
        Args:
            event: The raw event data
            
        Returns:
            True if event has required fields
        """
        return bool(event.get("current_stage")) or event.get("deal_value", 0) > 0

    def score_from_phase0_metrics(
        self,
        computed_metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        """
        Score revenue performance from Phase 0 computed_metrics.

        Uses pipeline data — deal counts, average deal size, conversion
        rates, and pipeline velocity — to derive a portfolio-level revenue
        health score.

        Signal composition:
        - pipeline_velocity (weight 0.35): Actual vs benchmark velocity
        - conversion_rate (weight 0.30): Deal conversion effectiveness
        - deal_volume score (weight 0.20): Log-scaled deal count
        - avg_deal_size vs segment benchmark (weight 0.15)

        Baseline: 1.0 (on-track revenue performance)
        """
        import math
        context = context or {}

        total_deals = computed_metrics.get("total_deals", 0)
        avg_deal_size = computed_metrics.get("avg_deal_size", 0)
        conversion_rate = computed_metrics.get("conversion_rate", 0.0)
        pipeline_velocity = computed_metrics.get("pipeline_velocity", 1.0)
        total_revenue = computed_metrics.get("total_revenue", 0)
        total_records = computed_metrics.get("total_records", 0)

        # Determine segment for benchmark comparison
        segment = context.get("segment", "default")
        benchmarks = self.SEGMENT_BENCHMARKS.get(segment, self.SEGMENT_BENCHMARKS["default"])
        benchmark_deal_size = benchmarks["avg_deal_size"]
        benchmark_win_rate = benchmarks["typical_win_rate"]

        # Velocity score: actual vs expected (1.0 = on track)
        velocity_score = float(pipeline_velocity) if isinstance(pipeline_velocity, (int, float)) else 1.0

        # Conversion score: actual vs benchmark
        conv_float = float(conversion_rate) if isinstance(conversion_rate, (int, float)) else 0.0
        conversion_score = (conv_float / benchmark_win_rate) if benchmark_win_rate > 0 else conv_float

        # Deal volume score: log-scaled, 1.0 at ~1000 deals
        deal_count = int(total_deals) if isinstance(total_deals, (int, float)) else 0
        volume_score = min(1.0, math.log10(max(deal_count, 1)) / 3.0) if deal_count > 0 else 0.0

        # Deal size score: actual vs benchmark
        deal_float = float(avg_deal_size) if isinstance(avg_deal_size, (int, float)) else 0.0
        size_score = (deal_float / benchmark_deal_size) if benchmark_deal_size > 0 else 0.5

        # Composite signal
        signal = (
            velocity_score * 0.35
            + conversion_score * 0.30
            + volume_score * 0.20
            + min(size_score, 2.0) * 0.15  # cap size score at 2x
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

        final_score = (signal / baseline) * multiplier if baseline > 0 else signal

        # Confidence
        volume_conf = min(0.2, math.log10(max(deal_count, 1)) / 3.0 * 0.2)
        data_conf = avg_pop * 0.2
        has_velocity = 0.1 if pipeline_velocity != 1.0 else 0.0
        confidence = min(0.95, 0.3 + volume_conf + data_conf + has_velocity)

        return ScoringResult(
            signal=signal,
            baseline=baseline,
            score=final_score,
            context_multiplier=multiplier,
            confidence=confidence,
            components={
                "velocity_score": velocity_score,
                "conversion_score": conversion_score,
                "volume_score": volume_score,
                "deal_size_score": size_score,
                "total_deals": deal_count,
                "avg_deal_size": deal_float,
                "total_revenue": float(total_revenue) if isinstance(total_revenue, (int, float)) else 0.0,
                "segment": segment,
                "source": "phase0",
            },
            explanation=(
                f"Phase 0 revenue: velocity={velocity_score:.2f}, "
                f"conversion={conv_float:.1%} (vs {benchmark_win_rate:.1%}), "
                f"deals={deal_count}, avg_size=${deal_float:,.0f} → score={final_score:.2f}"
            ),
            domain="revenue",
        )


__all__ = ["RevenueAdapter"]
