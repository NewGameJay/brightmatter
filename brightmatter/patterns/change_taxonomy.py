"""Change-type taxonomy — standardizes Google Ads change_event resource types
into the categories episodes are grouped and reasoned about by.

A change_event's (change_type, resource_type) is mapped to one category. The
category is what an episode is keyed on (account x campaign x category x day),
and what cross-account aggregation will later group by.
"""

from __future__ import annotations

# resource_type -> standardized change category. Resource type is the primary
# signal (it says WHAT was changed); change_type (CREATE/UPDATE/REMOVE) is the
# operation, kept separately on the episode.
_RESOURCE_TO_CATEGORY = {
    "CAMPAIGN_BUDGET": "budget",
    "BIDDING_STRATEGY": "bidding",
    "CAMPAIGN": "campaign_setting",          # status, bidding, settings on the campaign
    "CAMPAIGN_CRITERION": "targeting_keyword",  # campaign-level keywords/geo/audience/negatives
    "AD_GROUP_CRITERION": "targeting_keyword",  # ad-group keywords/audiences
    "AD_GROUP_AD": "ad_creative",
    "AD": "ad_creative",
    "AD_GROUP": "structure",
    "ASSET": "asset",
    "ASSET_SET_ASSET": "asset",
    "ASSET_SET": "asset",
    "CAMPAIGN_ASSET": "asset",
    "CAMPAIGN_ASSET_SET": "asset",
    "AD_GROUP_ASSET": "asset",
    "CUSTOMER_ASSET": "asset",
    "CONVERSION_ACTION": "conversion",
    "CUSTOMER_CONVERSION_GOAL": "conversion",
    "CAMPAIGN_CONVERSION_GOAL": "conversion",
}

# Categories that move spend/targeting/bids — the ones whose before/after is
# most worth a marketer's attention. (asset/structure are lower-stakes.)
HIGH_IMPACT = {"budget", "bidding", "campaign_setting", "targeting_keyword", "conversion"}

_LABELS = {
    "budget": "budget change",
    "bidding": "bidding-strategy change",
    "campaign_setting": "campaign-setting change",
    "targeting_keyword": "keyword/targeting change",
    "ad_creative": "ad/creative change",
    "asset": "asset/extension change",
    "structure": "ad-group/structure change",
    "conversion": "conversion-tracking change",
    "other": "other change",
}


def categorize(resource_type: str | None) -> str:
    """Map a change_event resource_type to a standardized category."""
    return _RESOURCE_TO_CATEGORY.get((resource_type or "").upper(), "other")


def label(category: str) -> str:
    """Human-readable phrase for a category (for episode descriptions)."""
    return _LABELS.get(category, category)
