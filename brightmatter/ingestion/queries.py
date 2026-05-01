"""GAQL query definitions for each ingestion tier.

Tier 1 (daily): campaign-level performance metrics
Tier 2 (weekly): keyword Quality Score and match type data
Tier 3 (on-change): change history events
"""

# ── Tier 1: Daily campaign performance ──

DAILY_CAMPAIGN_METRICS = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign.campaign_budget,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value,
  metrics.search_impression_share,
  metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share,
  metrics.search_absolute_top_impression_share,
  segments.date
FROM campaign
WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
  AND campaign.status != 'REMOVED'
"""

CAMPAIGN_CONFIG = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  campaign.bidding_strategy_type,
  campaign.campaign_budget,
  campaign.network_settings.target_google_search,
  campaign.network_settings.target_search_network,
  campaign.network_settings.target_content_network,
  campaign.geo_target_type_setting.positive_geo_target_type,
  campaign.start_date,
  campaign.end_date
FROM campaign
WHERE campaign.status != 'REMOVED'
"""

CAMPAIGN_BUDGET = """
SELECT
  campaign_budget.id,
  campaign_budget.name,
  campaign_budget.amount_micros,
  campaign_budget.type,
  campaign_budget.explicitly_shared
FROM campaign_budget
"""

CONVERSION_ACTIONS = """
SELECT
  conversion_action.id,
  conversion_action.name,
  conversion_action.status,
  conversion_action.type,
  conversion_action.category,
  conversion_action.primary_for_goal,
  conversion_action.counting_type,
  conversion_action.attribution_model_settings.attribution_model
FROM conversion_action
"""

# ── Tier 2: Weekly keyword data ──

KEYWORD_QUALITY_SCORES = """
SELECT
  ad_group.id,
  ad_group.name,
  ad_group_criterion.criterion_id,
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type,
  ad_group_criterion.quality_info.quality_score,
  ad_group_criterion.quality_info.creative_quality_score,
  ad_group_criterion.quality_info.post_click_quality_score,
  ad_group_criterion.quality_info.search_predicted_ctr,
  campaign.id,
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  segments.date
FROM keyword_view
WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
  AND campaign.status = 'ENABLED'
  AND ad_group.status = 'ENABLED'
  AND ad_group_criterion.status = 'ENABLED'
"""

# ── Tier 3: Change history ──

CHANGE_EVENTS = """
SELECT
  change_event.change_date_time,
  change_event.change_resource_type,
  change_event.change_resource_name,
  change_event.resource_change_operation,
  change_event.changed_fields,
  change_event.old_resource,
  change_event.new_resource,
  change_event.client_type,
  change_event.user_email,
  change_event.campaign,
  change_event.ad_group
FROM change_event
WHERE change_event.change_date_time >= '{start_date}'
  AND change_event.change_date_time <= '{end_date}'
ORDER BY change_event.change_date_time DESC
LIMIT 10000
"""

# ── Negative keywords (individual rows, aggregate in Python) ──

NEGATIVE_KEYWORDS = """
SELECT
  campaign.id,
  campaign.name,
  campaign_criterion.keyword.text,
  campaign_criterion.keyword.match_type
FROM campaign_criterion
WHERE campaign_criterion.negative = true
  AND campaign_criterion.type = 'KEYWORD'
  AND campaign.status = 'ENABLED'
"""

# ── Active keywords with match types (individual rows, aggregate in Python) ──

ACTIVE_KEYWORDS = """
SELECT
  campaign.id,
  campaign.name,
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type
FROM keyword_view
WHERE campaign.status = 'ENABLED'
  AND ad_group.status = 'ENABLED'
  AND ad_group_criterion.status = 'ENABLED'
  AND segments.date DURING LAST_7_DAYS
"""

# ── Extension / asset coverage ──

CAMPAIGN_ASSETS = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  asset.type,
  asset.name,
  campaign_asset.status
FROM campaign_asset
WHERE campaign.status = 'ENABLED'
"""

# ── Account discovery ──

ACCOUNT_INFO = """
SELECT
  customer.id,
  customer.descriptive_name,
  customer.currency_code,
  customer.manager
FROM customer
LIMIT 1
"""

ACCESSIBLE_ACCOUNTS = """
SELECT
  customer_client.id,
  customer_client.descriptive_name,
  customer_client.currency_code,
  customer_client.manager,
  customer_client.status
FROM customer_client
WHERE customer_client.manager = false
  AND customer_client.status = 'ENABLED'
"""
