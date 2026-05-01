"""Performance metrics models — daily campaign metrics and weekly keyword data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, computed_field


class DailyMetrics(BaseModel):
    """Campaign-level daily performance — Tier 1 ingestion."""

    account_id: str
    campaign_id: str
    campaign_name: str = ""
    campaign_type: str = ""
    date: date
    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    conversion_value: float = 0.0
    search_impression_share: Optional[float] = None
    search_budget_lost_is: Optional[float] = None
    search_rank_lost_is: Optional[float] = None
    search_abs_top_is: Optional[float] = None
    bidding_strategy: str = ""
    bidding_target: Optional[float] = None
    daily_budget_micros: int = 0
    status: str = "ENABLED"
    ingested_at: Optional[datetime] = None

    @computed_field
    @property
    def cost(self) -> float:
        return self.cost_micros / 1_000_000

    @computed_field
    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions > 0 else 0.0

    @computed_field
    @property
    def avg_cpc(self) -> float:
        return self.cost / self.clicks if self.clicks > 0 else 0.0

    @computed_field
    @property
    def cvr(self) -> float:
        return self.conversions / self.clicks if self.clicks > 0 else 0.0

    @computed_field
    @property
    def cpa(self) -> float:
        return self.cost / self.conversions if self.conversions > 0 else 0.0

    @computed_field
    @property
    def roas(self) -> float:
        return self.conversion_value / self.cost if self.cost > 0 else 0.0


class KeywordMetrics(BaseModel):
    """Keyword-level data with Quality Score — Tier 2 ingestion (weekly)."""

    account_id: str
    campaign_id: str
    ad_group_id: str
    keyword_id: str
    keyword_text: str = ""
    match_type: str = ""
    week_start: date
    quality_score: Optional[int] = None
    expected_ctr: str = ""
    ad_relevance: str = ""
    landing_page_experience: str = ""
    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    ingested_at: Optional[datetime] = None
