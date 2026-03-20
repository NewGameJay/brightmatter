"""
Channel Configuration Registry

Maps marketing channels to measurement parameters for the universal
resonance formula.  Each channel defines its primary signal, temporal
dynamics (decay, measurement window), context multipliers, and noise
thresholds.

Follows BrightMatter whitepaper Section 6.2 (Platform Normalization).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..types import Domain


@dataclass
class ChannelConfig:
    channel_id: str                     # "paid_social.meta", "email.lifecycle"
    display_name: str                   # "Meta Paid Social"
    domain: Domain                      # Which domain adapter provides scoring logic

    primary_signal: str                 # "roas" | "cpl" | "open_rate" | "conversion_rate"
    secondary_signals: List[str] = field(default_factory=list)

    # Temporal dynamics
    decay_half_life_hours: float = 72.0
    measurement_window_hours: float = 24.0
    full_measurement_days: int = 7

    # Context multipliers
    seasonality_weight: float = 0.0
    budget_sensitivity: float = 0.0

    # Noise thresholds
    min_sample_size: int = 30
    outlier_threshold_sigma: float = 3.0

    def to_dict(self) -> Dict:
        return {
            "channel_id": self.channel_id,
            "display_name": self.display_name,
            "domain": self.domain.value,
            "primary_signal": self.primary_signal,
            "secondary_signals": self.secondary_signals,
            "decay_half_life_hours": self.decay_half_life_hours,
            "measurement_window_hours": self.measurement_window_hours,
            "full_measurement_days": self.full_measurement_days,
            "seasonality_weight": self.seasonality_weight,
            "budget_sensitivity": self.budget_sensitivity,
            "min_sample_size": self.min_sample_size,
            "outlier_threshold_sigma": self.outlier_threshold_sigma,
        }


# ── Initial Registry ────────────────────────────────────────────────

CHANNEL_REGISTRY: Dict[str, ChannelConfig] = {
    "paid_social.meta": ChannelConfig(
        channel_id="paid_social.meta",
        display_name="Meta Paid Social",
        domain=Domain.CAMPAIGN,
        primary_signal="roas",
        secondary_signals=["ctr", "cpc", "cpm", "thumb_stop_rate", "hook_rate"],
        decay_half_life_hours=72,
        measurement_window_hours=24,
        full_measurement_days=7,
        seasonality_weight=0.3,
        budget_sensitivity=0.5,
    ),
    "paid_social.tiktok": ChannelConfig(
        channel_id="paid_social.tiktok",
        display_name="TikTok Paid Social",
        domain=Domain.CAMPAIGN,
        primary_signal="roas",
        secondary_signals=["ctr", "video_completion_rate", "engagement_rate"],
        decay_half_life_hours=48,
        measurement_window_hours=12,
        full_measurement_days=5,
        seasonality_weight=0.2,
        budget_sensitivity=0.4,
    ),
    "paid_search.google": ChannelConfig(
        channel_id="paid_search.google",
        display_name="Google Search Ads",
        domain=Domain.CAMPAIGN,
        primary_signal="roas",
        secondary_signals=["quality_score", "cpc", "impression_share", "conversion_rate"],
        decay_half_life_hours=168,
        measurement_window_hours=48,
        full_measurement_days=14,
        seasonality_weight=0.2,
        budget_sensitivity=0.6,
    ),
    "email.lifecycle": ChannelConfig(
        channel_id="email.lifecycle",
        display_name="Lifecycle Email",
        domain=Domain.HEALTH,
        primary_signal="revenue_per_recipient",
        secondary_signals=["open_rate", "click_rate", "conversion_rate", "unsubscribe_rate"],
        decay_half_life_hours=24,
        measurement_window_hours=4,
        full_measurement_days=7,
        seasonality_weight=0.1,
        budget_sensitivity=0.0,
    ),
    "email.broadcast": ChannelConfig(
        channel_id="email.broadcast",
        display_name="Broadcast Email",
        domain=Domain.CONTENT,
        primary_signal="open_rate",
        secondary_signals=["click_rate", "forward_rate", "revenue_per_send"],
        decay_half_life_hours=24,
        measurement_window_hours=2,
        full_measurement_days=3,
    ),
    "organic_social.instagram": ChannelConfig(
        channel_id="organic_social.instagram",
        display_name="Instagram Organic",
        domain=Domain.CONTENT,
        primary_signal="engagement_rate",
        secondary_signals=["reach", "save_rate", "share_rate", "follower_growth"],
        decay_half_life_hours=72,
        measurement_window_hours=6,
        full_measurement_days=7,
    ),
    "organic_social.tiktok": ChannelConfig(
        channel_id="organic_social.tiktok",
        display_name="TikTok Organic",
        domain=Domain.CONTENT,
        primary_signal="engagement_rate",
        secondary_signals=["video_views", "completion_rate", "share_rate"],
        decay_half_life_hours=48,
        measurement_window_hours=6,
        full_measurement_days=5,
    ),
    "organic_social.linkedin": ChannelConfig(
        channel_id="organic_social.linkedin",
        display_name="LinkedIn Organic",
        domain=Domain.CONTENT,
        primary_signal="engagement_rate",
        secondary_signals=["impressions", "click_rate", "comment_quality"],
        decay_half_life_hours=120,
        measurement_window_hours=24,
        full_measurement_days=14,
    ),
    "seo.content": ChannelConfig(
        channel_id="seo.content",
        display_name="SEO Content",
        domain=Domain.CONTENT,
        primary_signal="organic_traffic",
        secondary_signals=["ranking_position", "time_on_page", "bounce_rate", "backlinks"],
        decay_half_life_hours=336,
        measurement_window_hours=168,
        full_measurement_days=30,
    ),
    "sms_push.promotional": ChannelConfig(
        channel_id="sms_push.promotional",
        display_name="SMS/Push Promotional",
        domain=Domain.CAMPAIGN,
        primary_signal="conversion_rate",
        secondary_signals=["open_rate", "click_rate", "opt_out_rate"],
        decay_half_life_hours=4,
        measurement_window_hours=1,
        full_measurement_days=1,
    ),
    "landing_page": ChannelConfig(
        channel_id="landing_page",
        display_name="Landing Page / CRO",
        domain=Domain.CAMPAIGN,
        primary_signal="conversion_rate",
        secondary_signals=["bounce_rate", "scroll_depth", "time_on_page", "form_completion"],
        decay_half_life_hours=168,
        measurement_window_hours=48,
        full_measurement_days=14,
    ),
    "newsletter": ChannelConfig(
        channel_id="newsletter",
        display_name="Newsletter",
        domain=Domain.CONTENT,
        primary_signal="open_rate",
        secondary_signals=["click_rate", "subscriber_growth", "forward_rate", "engagement_depth"],
        decay_half_life_hours=48,
        measurement_window_hours=4,
        full_measurement_days=3,
    ),
    "pr.earned_media": ChannelConfig(
        channel_id="pr.earned_media",
        display_name="PR / Earned Media",
        domain=Domain.CONTENT,
        primary_signal="pickup_rate",
        secondary_signals=["domain_authority_avg", "referral_traffic", "social_amplification"],
        decay_half_life_hours=168,
        measurement_window_hours=48,
        full_measurement_days=14,
    ),
    "sales.outbound": ChannelConfig(
        channel_id="sales.outbound",
        display_name="Sales Outbound",
        domain=Domain.REVENUE,
        primary_signal="reply_rate",
        secondary_signals=["meeting_booked_rate", "open_rate", "bounce_rate"],
        decay_half_life_hours=72,
        measurement_window_hours=24,
        full_measurement_days=7,
    ),
}


# ── Lookup helpers ──────────────────────────────────────────────────

def get_channel_config(channel_id: str) -> Optional[ChannelConfig]:
    """Look up channel config by ID. Returns ``None`` for unknown channels."""
    return CHANNEL_REGISTRY.get(channel_id)


def get_channels_for_domain(domain: Domain) -> List[ChannelConfig]:
    """Get all channels that use a specific domain adapter."""
    return [c for c in CHANNEL_REGISTRY.values() if c.domain == domain]


SKILL_CHANNEL_MAP: Dict[str, str] = {
    "email-copy-generator": "email.broadcast",
    "cohort-email-builder": "email.lifecycle",
    "lifecycle-communications-sequences": "email.lifecycle",
    "cold-email-personalization": "sales.outbound",
    "seo-content": "seo.content",
    "direct-response-copy": "paid_social.meta",
    "ghostwrite-content": "organic_social.instagram",
    "positioning-angles": "landing_page",
    "social-listening-collect": "organic_social.instagram",
    "linkedin-keyword-search": "organic_social.linkedin",
    "creative-brief": "paid_social.meta",
    "page-cro": "landing_page",
    "programmatic-seo": "seo.content",
    "experiment-roadmap": "landing_page",
}


def infer_channel_from_skill(skill_name: str) -> Optional[str]:
    """Infer ``channel_id`` from skill name. Returns ``None`` if ambiguous."""
    return SKILL_CHANNEL_MAP.get(skill_name)
