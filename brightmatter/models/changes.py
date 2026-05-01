"""Change tracking models — change events and episodes (change-to-outcome pairs)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChangeActor(str, Enum):
    """Who made the change — critical for detecting auto-applied recommendations."""

    HUMAN = "human"
    AUTO_APPLIED = "auto_applied"
    GOOGLE_ADS = "google_ads"
    UNKNOWN = "unknown"


class ChangeEvent(BaseModel):
    """A single change recorded in Google Ads Change History — Tier 3 ingestion."""

    account_id: str
    change_id: str
    change_timestamp: datetime
    change_type: str = ""
    resource_type: str = ""
    resource_name: str = ""
    campaign_id: str = ""
    campaign_name: str = ""
    actor: ChangeActor = ChangeActor.UNKNOWN
    actor_email: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    ingested_at: Optional[datetime] = None


class EpisodeOutcome(str, Enum):
    IMPROVED = "improved"
    DEGRADED = "degraded"
    NEUTRAL = "neutral"
    PENDING = "pending"


class Episode(BaseModel):
    """A change-to-outcome pair: what changed, what happened before and after.

    This is BrightMatter's core learning unit. Every change becomes an episode
    once enough post-change data exists to measure the outcome.
    """

    episode_id: str
    account_id: str
    change_event_id: str
    change_description: str = ""
    domain: str = ""
    pre_metrics: dict[str, Any] = Field(default_factory=dict)
    post_metrics: dict[str, Any] = Field(default_factory=dict)
    outcome: EpisodeOutcome = EpisodeOutcome.PENDING
    outcome_magnitude: float = 0.0
    outcome_detail: str = ""
    recorded_at: Optional[datetime] = None
