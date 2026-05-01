"""Account and campaign models — the structural skeleton of every Google Ads account."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BusinessType(str, Enum):
    ECOMMERCE = "ecommerce"
    LEAD_GEN = "lead_gen"
    SAAS = "saas"
    LOCAL = "local"
    B2B = "b2b"
    APP = "app"
    UNKNOWN = "unknown"


class SpendTier(str, Enum):
    MICRO = "<5k"
    SMALL = "5k-25k"
    MID = "25k-100k"
    LARGE = "100k+"


class CampaignType(str, Enum):
    SEARCH = "SEARCH"
    PERFORMANCE_MAX = "PERFORMANCE_MAX"
    SHOPPING = "SHOPPING"
    DISPLAY = "DISPLAY"
    VIDEO = "VIDEO"
    DEMAND_GEN = "DEMAND_GEN"
    APP = "APP"
    SMART = "SMART"
    UNKNOWN = "UNKNOWN"


class BiddingStrategy(str, Enum):
    TARGET_CPA = "TARGET_CPA"
    TARGET_ROAS = "TARGET_ROAS"
    MAXIMIZE_CONVERSIONS = "MAXIMIZE_CONVERSIONS"
    MAXIMIZE_CONVERSION_VALUE = "MAXIMIZE_CONVERSION_VALUE"
    MAXIMIZE_CLICKS = "MAXIMIZE_CLICKS"
    TARGET_IMPRESSION_SHARE = "TARGET_IMPRESSION_SHARE"
    MANUAL_CPC = "MANUAL_CPC"
    MANUAL_CPM = "MANUAL_CPM"
    UNKNOWN = "UNKNOWN"


class Account(BaseModel):
    account_id: str
    account_name: str = ""
    mcc_id: str = ""
    business_type: BusinessType = BusinessType.UNKNOWN
    vertical: str = ""
    website_url: str = ""
    spend_tier: SpendTier = SpendTier.MICRO
    currency_code: str = "USD"
    first_seen: Optional[date] = None
    last_updated: Optional[datetime] = None


class CampaignConfig(BaseModel):
    """Point-in-time snapshot of a campaign's configuration."""

    campaign_id: str
    campaign_name: str = ""
    campaign_type: CampaignType = CampaignType.UNKNOWN
    status: str = "ENABLED"
    bidding_strategy: BiddingStrategy = BiddingStrategy.UNKNOWN
    bidding_target: Optional[float] = None
    daily_budget_micros: int = 0
    network_search: bool = True
    network_search_partners: bool = False
    network_display: bool = False
    geo_targets: list[str] = Field(default_factory=list)
    language_codes: list[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class Campaign(BaseModel):
    """A campaign with its current config and parent account reference."""

    account_id: str
    config: CampaignConfig
    snapshot_date: date
