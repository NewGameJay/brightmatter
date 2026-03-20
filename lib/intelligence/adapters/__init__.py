"""
MH1 Intelligence Domain Adapters

Pluggable adapters for domain-specific scoring:
- Content: Engagement, impressions, growth
- Revenue: Deal velocity, pipeline health
- Health: Customer health, churn risk
- Campaign: ROI, attribution, efficiency

Universal Scoring Formula:
    Score = (Signal / Baseline) × Context × Confidence
"""

from .base import BaseDomainAdapter, ScoringResult
from .campaign import CampaignAdapter
from .channels import ChannelConfig, CHANNEL_REGISTRY, get_channel_config, get_channels_for_domain, infer_channel_from_skill
from .content import ContentAdapter
from .health import HealthAdapter
from .revenue import RevenueAdapter

__all__ = [
    "BaseDomainAdapter",
    "ScoringResult",
    "CampaignAdapter",
    "ChannelConfig",
    "CHANNEL_REGISTRY",
    "ContentAdapter",
    "HealthAdapter",
    "RevenueAdapter",
    "get_channel_config",
    "get_channels_for_domain",
    "infer_channel_from_skill",
]
