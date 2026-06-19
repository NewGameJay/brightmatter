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
    CONFOUNDED = "confounded"   # other change categories hit the same campaign in the window
    PENDING = "pending"


class Episode(BaseModel):
    """A change-to-outcome pair: what changed, what happened before and after.

    Phase 1.5: an episode is a BATCH of same-category changes on one campaign on
    one day (not one per raw change event), measured against pre/post windows.
    PRELIMINARY by construction — it records what happened, never claims
    causation, and carries no trend adjustment (that is Phase 2).
    """

    episode_id: str
    account_id: str
    change_event_id: str          # representative event id for the batch
    campaign_id: str = ""
    change_description: str = ""
    domain: str = ""
    change_category: str = ""     # taxonomy: budget / bidding / targeting_keyword / ...
    change_count: int = 1         # how many raw change events in the batch
    actor: str = ""               # auto_applied / human / mixed
    confounded: bool = False      # other change categories hit the campaign in the window
    pre_metrics: dict[str, Any] = Field(default_factory=dict)
    post_metrics: dict[str, Any] = Field(default_factory=dict)
    outcome: EpisodeOutcome = EpisodeOutcome.PENDING
    outcome_magnitude: float = 0.0
    outcome_detail: str = ""
    # Confidence framing (same honesty layer as signals) — preliminary, no causation.
    confidence_tier: str = ""
    what_we_know: str = ""
    what_we_cant_rule_out: str = ""
    check_next: str = ""
    # Phase 2.3 — trend-adjusted attribution. outcome/outcome_magnitude hold the
    # ADJUSTED values once adjusted; raw_magnitude preserves the pre-adjustment one.
    trend_adjusted: bool = False
    trend_slope: float = 0.0          # pre-change daily slope of the primary metric
    expected_value: float = 0.0       # where the metric would be at post-window end sans change
    raw_magnitude: float = 0.0        # |actual - pre| / pre  (pre-adjustment)
    adjusted_magnitude: float = 0.0   # |actual - expected| / pre  (the change's contribution)
    trend_contribution_pct: float = 0.0  # share of the raw move explained by pre-existing trend
    recorded_at: Optional[datetime] = None
