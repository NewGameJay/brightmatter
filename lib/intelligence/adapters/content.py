"""
MH1 Intelligence Content Domain Adapter

Scoring adapter for content and engagement metrics across platforms.
Handles social media (LinkedIn, Twitter, Instagram), email campaigns,
and other content types with platform-specific engagement rates and decay.

Content scoring considers:
- Impressions and reach
- Engagements (likes, comments, shares, clicks)
- Platform-specific baseline rates
- Content decay over time (viral half-life)
- Content type and format bonuses
- Paid vs organic performance

The Signal/Baseline formula for content:
    signal = impressions * (1 + engagement_rate)
    baseline = follower_count * platform_rate * decay_factor
    score = (signal / baseline) * context_multiplier
"""

from typing import Any, Dict, Optional

from .base import BaseDomainAdapter, ScoringResult


class ContentAdapter(BaseDomainAdapter):
    """
    Domain adapter for content and engagement scoring.
    
    Calculates performance scores for content across various platforms
    by comparing actual engagement against expected baselines based on
    audience size, platform norms, and content age.
    
    Platform-specific considerations:
    - LinkedIn: Professional content, slower decay, moderate engagement
    - Twitter: Fast-moving, rapid decay, lower engagement rates
    - Instagram: Visual content, moderate decay, higher engagement
    - Email: Direct channel, slow decay, highest engagement when opened
    
    The adapter handles both organic and paid content, with multipliers
    for content type (video > image > text) and sentiment.
    """
    
    # Platform-specific baseline rates and decay characteristics
    PLATFORM_RATES = {
        "linkedin": {
            "engagement_rate": 0.02,      # 2% baseline engagement
            "impression_rate": 0.10,       # 10% of followers see content
            "decay_half_life_hours": 24    # Content relevance halves every 24h
        },
        "twitter": {
            "engagement_rate": 0.015,      # 1.5% baseline engagement
            "impression_rate": 0.08,       # 8% of followers see content
            "decay_half_life_hours": 4     # Very fast decay
        },
        "instagram": {
            "engagement_rate": 0.03,       # 3% baseline engagement
            "impression_rate": 0.15,       # 15% of followers see content
            "decay_half_life_hours": 12    # Moderate decay
        },
        "email": {
            "engagement_rate": 0.20,       # 20% click-through baseline (of opens)
            "impression_rate": 0.25,       # 25% open rate baseline
            "decay_half_life_hours": 48    # Email relevance lasts longer
        },
        "default": {
            "engagement_rate": 0.02,       # Conservative 2% default
            "impression_rate": 0.10,       # 10% default reach
            "decay_half_life_hours": 24    # 24h default half-life
        }
    }
    
    # Content type multipliers (video performs best)
    CONTENT_TYPE_MULTIPLIERS = {
        "video": 1.3,
        "image": 1.1,
        "carousel": 1.15,
        "text": 1.0,
        "link": 0.9,
        "default": 1.0
    }
    
    def get_domain_name(self) -> str:
        """
        Return the domain identifier for this adapter.
        
        Returns:
            "content" domain name
        """
        return "content"
    
    def get_signal(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Extract content engagement signal from an event.
        
        Formula: impressions * (1 + engagement_rate)
        
        This weights raw impressions by engagement quality. Content with
        high impressions but no engagement scores lower than content with
        fewer impressions but active engagement.
        
        Args:
            event: Event data containing:
                - impressions: Number of times content was shown
                - engagements: Total engagement count (optional)
                - likes: Like/reaction count (optional)
                - comments: Comment count (optional)
                - shares: Share/retweet count (optional)
            context: Additional context (not used for signal extraction)
            
        Returns:
            Weighted engagement signal value
        """
        impressions = float(event.get("impressions", 0))
        
        # Calculate total engagements from available metrics
        engagements = float(event.get("engagements", 0))
        if engagements == 0:
            # Sum individual engagement types if total not provided
            likes = float(event.get("likes", 0))
            comments = float(event.get("comments", 0))
            shares = float(event.get("shares", 0))
            clicks = float(event.get("clicks", 0))
            engagements = likes + comments + shares + clicks
        
        # Calculate engagement rate
        if impressions > 0:
            engagement_rate = engagements / impressions
        else:
            engagement_rate = 0.0
        
        # Signal = impressions weighted by engagement quality
        signal = impressions * (1 + engagement_rate)
        
        return signal
    
    def get_baseline(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate expected baseline performance for content.
        
        Formula: follower_count * platform_rate * decay_factor
        
        The baseline represents what we'd expect for typical content
        given the audience size, platform norms, and content age.
        
        Args:
            event: Event data containing:
                - platform: Platform name (linkedin, twitter, etc.)
                - hours_since_post: Hours since content was published (optional)
            context: Context containing:
                - follower_count: Audience size (default 1000)
                
        Returns:
            Expected baseline impression value
        """
        # Get follower count from context
        follower_count = float(context.get("follower_count", 1000))
        
        # Get platform configuration
        platform = event.get("platform", "default").lower()
        platform_config = self.PLATFORM_RATES.get(platform, self.PLATFORM_RATES["default"])
        impression_rate = platform_config["impression_rate"]
        
        # Calculate decay factor based on content age
        hours_since_post = float(event.get("hours_since_post", 0))
        decay_factor = self._calculate_decay(hours_since_post, platform)
        
        # Baseline = expected impressions for this audience and platform
        baseline = follower_count * impression_rate * decay_factor
        
        # Ensure minimum baseline to avoid division issues
        return max(baseline, 1.0)
    
    def get_context_multiplier(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate context-based adjustments for content scoring.
        
        Considers:
        - Sentiment score: Negative sentiment reduces expected performance
        - Paid promotion: Paid content expected to perform better
        - Content type: Video > Image > Text
        
        Args:
            event: Event data containing:
                - sentiment_score: Sentiment from -1 to 1 (optional)
                - is_paid: Whether content was promoted (optional)
                - content_type: Type of content (video, image, text) (optional)
            context: Additional context (not directly used)
            
        Returns:
            Combined context multiplier (typically 0.5 to 2.0)
        """
        multiplier = 1.0
        
        # Sentiment adjustment: map [-1, 1] to [0.5, 1.5]
        sentiment_score = event.get("sentiment_score")
        if sentiment_score is not None:
            sentiment_score = float(sentiment_score)
            # Clamp to valid range
            sentiment_score = max(-1.0, min(1.0, sentiment_score))
            # Map -1..1 to 0.5..1.5
            sentiment_multiplier = 1.0 + (sentiment_score * 0.5)
            multiplier *= sentiment_multiplier
        
        # Paid promotion boost
        is_paid = event.get("is_paid", False)
        if is_paid:
            multiplier *= 1.2
        
        # Content type multiplier
        content_type = event.get("content_type", "default").lower()
        type_multiplier = self.CONTENT_TYPE_MULTIPLIERS.get(
            content_type, 
            self.CONTENT_TYPE_MULTIPLIERS["default"]
        )
        multiplier *= type_multiplier
        
        return multiplier
    
    def _calculate_decay(self, hours_since_post: float, platform: str) -> float:
        """
        Calculate content decay factor based on platform half-life.
        
        Uses exponential decay: decay = 0.5 ^ (hours / half_life)
        
        Content performance naturally declines over time. Different platforms
        have different decay rates - Twitter content becomes stale quickly,
        while LinkedIn posts have longer relevance windows.
        
        Args:
            hours_since_post: Hours since content was published
            platform: Platform name for half-life lookup
            
        Returns:
            Decay factor between 0.1 (minimum) and 1.0 (no decay)
        """
        if hours_since_post <= 0:
            return 1.0
        
        # Get platform-specific half-life
        platform_config = self.PLATFORM_RATES.get(
            platform.lower(), 
            self.PLATFORM_RATES["default"]
        )
        half_life = platform_config["decay_half_life_hours"]
        
        # Exponential decay formula
        decay = 0.5 ** (hours_since_post / half_life)
        
        # Minimum 10% baseline - old content still has some residual value
        return max(decay, 0.1)
    
    def _calculate_confidence(self, event: Dict[str, Any], context: Dict[str, Any]) -> float:
        """
        Calculate confidence in the scoring result based on data quality.
        
        Higher confidence when:
        - More impressions (statistically significant sample)
        - More engagements (signal is real, not noise)
        - Known follower count (baseline is accurate)
        
        Args:
            event: Event data with metrics
            context: Context with audience info
            
        Returns:
            Confidence value between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence
        
        # Boost for significant impression count
        impressions = float(event.get("impressions", 0))
        if impressions > 100:
            confidence += 0.1
        if impressions > 1000:
            confidence += 0.1
        
        # Boost for meaningful engagement
        engagements = float(event.get("engagements", 0))
        if engagements == 0:
            likes = float(event.get("likes", 0))
            comments = float(event.get("comments", 0))
            shares = float(event.get("shares", 0))
            engagements = likes + comments + shares
        
        if engagements > 10:
            confidence += 0.1
        if engagements > 100:
            confidence += 0.1
        
        # Boost for known follower count (better baseline)
        if "follower_count" in context:
            confidence += 0.1
        
        # Cap at 1.0
        return min(confidence, 1.0)
    
    def validate_event(self, event: Dict[str, Any]) -> bool:
        """
        Validate that an event has minimum required fields for scoring.
        
        Content events must have at least impressions or some form of
        engagement data to be scorable.
        
        Args:
            event: Event data to validate
            
        Returns:
            True if event can be scored, False otherwise
        """
        # Must have impressions or engagement data
        has_impressions = "impressions" in event and event["impressions"] is not None
        has_engagements = "engagements" in event and event["engagements"] is not None
        has_individual_engagements = any(
            key in event and event[key] is not None
            for key in ["likes", "comments", "shares", "clicks"]
        )
        
        return has_impressions or has_engagements or has_individual_engagements

    def score_from_phase0_metrics(
        self,
        computed_metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoringResult:
        """
        Score content performance from Phase 0 computed_metrics.

        Uses audience metrics (subscriber counts, engagement rates, content
        volume) to derive a portfolio-level content health score.

        Signal composition:
        - engagement_rate vs platform benchmark (weight 0.40)
        - audience_size (log-scaled, weight 0.25)
        - content_volume activity (weight 0.20)
        - audience_growth if available (weight 0.15)
        """
        import math
        context = context or {}

        engagement_rate = computed_metrics.get("engagement_rate", 0.0)
        total_contacts = computed_metrics.get("total_contacts", 0)
        audience_size = computed_metrics.get("audience_size", total_contacts)
        content_count = computed_metrics.get("total_content", computed_metrics.get("total_campaigns", 0))
        audience_growth = computed_metrics.get("audience_growth_rate", 0.0)
        total_records = computed_metrics.get("total_records", 0)

        # Ensure floats
        engagement_rate = float(engagement_rate) if isinstance(engagement_rate, (int, float)) else 0.0
        audience_size = int(audience_size) if isinstance(audience_size, (int, float)) else 0
        content_count = int(content_count) if isinstance(content_count, (int, float)) else 0
        audience_growth = float(audience_growth) if isinstance(audience_growth, (int, float)) else 0.0

        # Benchmark engagement (blended across platforms)
        benchmark_engagement = context.get("benchmark_engagement_rate", 0.03)

        # Scores
        engagement_score = (engagement_rate / benchmark_engagement) if benchmark_engagement > 0 else 0.5
        audience_score = min(1.0, math.log10(max(audience_size, 1)) / 6.0) if audience_size > 0 else 0.0
        content_score = min(1.0, math.log10(max(content_count, 1)) / 3.0) if content_count > 0 else 0.0
        growth_score = min(1.5, 0.5 + audience_growth * 10)  # 5% growth → 1.0

        signal = (
            min(engagement_score, 2.0) * 0.40
            + audience_score * 0.25
            + content_score * 0.20
            + growth_score * 0.15
        )

        baseline = 1.0

        # Data quality
        field_pop = computed_metrics.get("field_population_rates", {})
        if isinstance(field_pop, dict) and field_pop:
            pop_vals = [v for v in field_pop.values() if isinstance(v, (int, float))]
            avg_pop = sum(pop_vals) / len(pop_vals) if pop_vals else 0.5
        else:
            avg_pop = 0.5
        multiplier = 0.9 + avg_pop * 0.2

        final_score = (signal / baseline) * multiplier

        confidence = min(0.95, 0.25 + (0.15 if engagement_rate > 0 else 0) + (0.1 if audience_size > 100 else 0) + avg_pop * 0.2)

        return ScoringResult(
            signal=signal,
            baseline=baseline,
            score=final_score,
            context_multiplier=multiplier,
            confidence=confidence,
            components={
                "engagement_rate": engagement_rate,
                "engagement_score": engagement_score,
                "audience_size": audience_size,
                "audience_score": audience_score,
                "content_count": content_count,
                "audience_growth": audience_growth,
                "source": "phase0",
            },
            explanation=(
                f"Phase 0 content: engagement={engagement_rate:.2%} "
                f"(vs {benchmark_engagement:.2%}), audience={audience_size:,}, "
                f"content_pieces={content_count} → score={final_score:.2f}"
            ),
            domain="content",
        )


__all__ = [
    "ContentAdapter",
]
