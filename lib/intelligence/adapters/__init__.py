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
from .content import ContentAdapter
from .health import HealthAdapter
from .revenue import RevenueAdapter

__all__ = [
    "BaseDomainAdapter",
    "ScoringResult",
    "CampaignAdapter",
    "ContentAdapter",
    "HealthAdapter",
    "RevenueAdapter",
]
