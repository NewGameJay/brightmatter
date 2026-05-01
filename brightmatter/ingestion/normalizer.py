"""Normalizer — converts raw Google Ads API row objects into Pydantic models."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

from brightmatter.models.account import Account, BiddingStrategy, CampaignType
from brightmatter.models.changes import ChangeActor, ChangeEvent
from brightmatter.models.metrics import DailyMetrics, KeywordMetrics

_CHANNEL_MAP = {
    "SEARCH": CampaignType.SEARCH,
    "PERFORMANCE_MAX": CampaignType.PERFORMANCE_MAX,
    "SHOPPING": CampaignType.SHOPPING,
    "DISPLAY": CampaignType.DISPLAY,
    "VIDEO": CampaignType.VIDEO,
    "DEMAND_GEN": CampaignType.DEMAND_GEN,
    "MULTI_CHANNEL": CampaignType.PERFORMANCE_MAX,
}

_BIDDING_MAP = {
    "TARGET_CPA": BiddingStrategy.TARGET_CPA,
    "TARGET_ROAS": BiddingStrategy.TARGET_ROAS,
    "MAXIMIZE_CONVERSIONS": BiddingStrategy.MAXIMIZE_CONVERSIONS,
    "MAXIMIZE_CONVERSION_VALUE": BiddingStrategy.MAXIMIZE_CONVERSION_VALUE,
    "MAXIMIZE_CLICKS": BiddingStrategy.MAXIMIZE_CLICKS,
    "TARGET_IMPRESSION_SHARE": BiddingStrategy.TARGET_IMPRESSION_SHARE,
    "MANUAL_CPC": BiddingStrategy.MANUAL_CPC,
    "MANUAL_CPM": BiddingStrategy.MANUAL_CPM,
}

_AUTO_ACTOR_TYPES = {
    "GOOGLE_ADS_WEB_CLIENT",
    "GOOGLE_ADS_AUTOMATED_RULE",
    "GOOGLE_ADS_SCRIPTS",
    "GOOGLE_ADS_BULK",
    "GOOGLE_ADS_RECOMMENDATIONS",
    "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION",
}


def _safe_name(enum_val: Any) -> str:
    return enum_val.name if hasattr(enum_val, "name") else str(enum_val)


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def normalize_daily_metrics(row: Any, account_id: str) -> DailyMetrics:
    campaign = row.campaign
    metrics = row.metrics
    seg = row.segments

    campaign_type = _safe_name(campaign.advertising_channel_type)
    bidding = _safe_name(campaign.bidding_strategy_type)

    return DailyMetrics(
        account_id=account_id,
        campaign_id=str(campaign.id),
        campaign_name=campaign.name,
        campaign_type=_CHANNEL_MAP.get(campaign_type, CampaignType.UNKNOWN).value,
        date=_parse_date(seg.date),
        impressions=metrics.impressions,
        clicks=metrics.clicks,
        cost_micros=metrics.cost_micros,
        conversions=metrics.conversions,
        conversion_value=metrics.conversions_value,
        search_impression_share=metrics.search_impression_share if metrics.search_impression_share else None,
        search_budget_lost_is=metrics.search_budget_lost_impression_share if metrics.search_budget_lost_impression_share else None,
        search_rank_lost_is=metrics.search_rank_lost_impression_share if metrics.search_rank_lost_impression_share else None,
        search_abs_top_is=metrics.search_absolute_top_impression_share if metrics.search_absolute_top_impression_share else None,
        bidding_strategy=_BIDDING_MAP.get(bidding, BiddingStrategy.UNKNOWN).value,
        daily_budget_micros=0,
        status=_safe_name(campaign.status),
    )


def normalize_keyword_metrics(row: Any, account_id: str, week_start: date) -> KeywordMetrics:
    ag = row.ad_group
    crit = row.ad_group_criterion
    metrics = row.metrics
    qi = crit.quality_info

    return KeywordMetrics(
        account_id=account_id,
        campaign_id=str(row.campaign.id),
        ad_group_id=str(ag.id),
        keyword_id=str(crit.criterion_id),
        keyword_text=crit.keyword.text,
        match_type=_safe_name(crit.keyword.match_type),
        week_start=week_start,
        quality_score=qi.quality_score if qi.quality_score else None,
        expected_ctr=_safe_name(qi.search_predicted_ctr) if qi.search_predicted_ctr else "",
        ad_relevance=_safe_name(qi.creative_quality_score) if qi.creative_quality_score else "",
        landing_page_experience=_safe_name(qi.post_click_quality_score) if qi.post_click_quality_score else "",
        impressions=metrics.impressions,
        clicks=metrics.clicks,
        cost_micros=metrics.cost_micros,
        conversions=metrics.conversions,
    )


def normalize_change_event(row: Any, account_id: str) -> ChangeEvent:
    ce = row.change_event
    client_type = _safe_name(ce.client_type)

    if client_type in _AUTO_ACTOR_TYPES:
        actor = ChangeActor.AUTO_APPLIED
    elif ce.user_email:
        actor = ChangeActor.HUMAN
    else:
        actor = ChangeActor.UNKNOWN

    change_id = hashlib.sha256(
        f"{account_id}:{ce.change_date_time}:{ce.change_resource_name}".encode()
    ).hexdigest()[:16]

    campaign_id = ""
    campaign_name = ""
    if ce.campaign:
        parts = ce.campaign.split("/")
        campaign_id = parts[-1] if parts else ""

    return ChangeEvent(
        account_id=account_id,
        change_id=change_id,
        change_timestamp=datetime.fromisoformat(ce.change_date_time.replace("Z", "+00:00"))
            if isinstance(ce.change_date_time, str)
            else datetime.now(timezone.utc),
        change_type=_safe_name(ce.resource_change_operation),
        resource_type=_safe_name(ce.change_resource_type),
        resource_name=ce.change_resource_name,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        actor=actor,
        actor_email=ce.user_email or "",
        old_value=str(ce.old_resource) if ce.old_resource else None,
        new_value=str(ce.new_resource) if ce.new_resource else None,
    )


def normalize_account(raw: dict[str, Any], mcc_id: str) -> Account:
    return Account(
        account_id=raw["id"],
        account_name=raw.get("name", ""),
        mcc_id=mcc_id,
        currency_code=raw.get("currency_code", "USD"),
        first_seen=date.today(),
        last_updated=datetime.now(timezone.utc),
    )
