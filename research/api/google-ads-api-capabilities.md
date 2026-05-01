# Google Ads API Capabilities for BrightMatter

> Mapping API data availability to BrightMatter's pattern detection needs across 500 accounts.
> Research compiled April 2026. Based on Google Ads API v19–v24.

---

## GAQL Query Patterns

### How Queries Work
Google Ads Query Language (GAQL) is SQL-like and runs against the `GoogleAdsService` via `Search` (paginated) or `SearchStream` (streaming) methods. Every query has the structure:

```sql
SELECT
  resource.field,
  metrics.metric,
  segments.segment
FROM resource
WHERE conditions
ORDER BY field
LIMIT n
```

### Key Rules
- **FROM** specifies the primary resource (e.g., `campaign`, `ad_group`, `keyword_view`, `change_event`)
- **Segments** in `SELECT` cause metrics to be split by that segment (e.g., `segments.date` creates per-day rows)
- **Not all fields are compatible**: Use `GoogleAdsFieldService` to check `selectable_with` for any field
- **No JOINs**: Attributed resources (e.g., `campaign` from `ad_group`) are implicitly joined
- **LIMIT** max 10,000 for `change_event`; pagination via `next_page_token` for other resources
- **IN clause** limited to 20,000 items

### Example Queries for Pattern Detection

**Daily campaign performance with CPC/CVR tracking:**
```sql
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.bidding_strategy_type,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value,
  metrics.cost_micros,
  metrics.average_cpc,
  metrics.ctr,
  metrics.conversions_from_interactions_rate,
  metrics.search_impression_share,
  metrics.search_budget_lost_impression_share,
  metrics.search_rank_lost_impression_share,
  segments.date
FROM campaign
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.status = 'ENABLED'
```

**Keyword-level Quality Score tracking:**
```sql
SELECT
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type,
  ad_group_criterion.quality_info.quality_score,
  ad_group_criterion.quality_info.creative_relevance,
  ad_group_criterion.quality_info.post_click_quality_score,
  ad_group_criterion.quality_info.search_predicted_ctr,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.average_cpc,
  segments.date
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.status = 'ENABLED'
  AND ad_group.status = 'ENABLED'
  AND ad_group_criterion.status = 'ENABLED'
```

**Auction Insights via keyword_view:**
```sql
SELECT
  campaign.id,
  campaign.name,
  ad_group_criterion.keyword.text,
  segments.auction_insight_domain,
  metrics.auction_insight_search_impression_share,
  metrics.auction_insight_search_overlap_rate,
  metrics.auction_insight_search_outranking_share,
  metrics.auction_insight_search_position_above_rate,
  metrics.auction_insight_search_absolute_top_impression_percentage,
  metrics.auction_insight_search_top_impression_percentage
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.status = 'ENABLED'
```

**Conversion action configuration audit:**
```sql
SELECT
  conversion_action.id,
  conversion_action.name,
  conversion_action.status,
  conversion_action.type,
  conversion_action.category,
  conversion_action.attribution_model_settings.attribution_model,
  conversion_action.counting_type,
  conversion_action.click_through_lookback_window_days,
  conversion_action.view_through_lookback_window_days,
  conversion_action.primary_for_goal
FROM conversion_action
```

### Date Range Options
GAQL supports both explicit dates and predefined ranges:
- `DURING LAST_7_DAYS`, `LAST_14_DAYS`, `LAST_30_DAYS`, `LAST_90_DAYS`
- `DURING THIS_MONTH`, `LAST_MONTH`, `THIS_QUARTER`
- Explicit: `segments.date BETWEEN '2026-01-01' AND '2026-01-31'`

---

## Change History Capabilities

### ChangeEvent Resource
The `change_event` resource provides the most detailed change tracking in the API:

**Fields available:**
| Field | Description |
|-------|-------------|
| `change_event.resource_name` | Unique identifier |
| `change_event.change_date_time` | When the change occurred |
| `change_event.change_resource_name` | Resource that was changed |
| `change_event.user_email` | Who made the change |
| `change_event.client_type` | How the change was made (API, UI, auto-applied, etc.) |
| `change_event.change_resource_type` | Type of resource changed |
| `change_event.resource_change_operation` | CREATE, UPDATE, or DELETE |
| `change_event.changed_fields` | List of specific fields modified |
| `change_event.old_resource` | Previous values (for UPDATE) |
| `change_event.new_resource` | New values (for CREATE and UPDATE) |

### Auto-Applied Detection — Critical for BrightMatter
The `client_type` enum (`ChangeClientType`) enables distinguishing human from automated changes:

| client_type Value | Description |
|-------------------|-------------|
| `GOOGLE_ADS_WEB_CLIENT` | Change made in Google Ads UI |
| `GOOGLE_ADS_SCRIPTS` | Change made by Google Ads Scripts |
| `GOOGLE_ADS_BULK_UPLOAD` | Bulk upload (Editor, CSV) |
| `GOOGLE_ADS_API` | Change made via API |
| `GOOGLE_ADS_AUTOMATED_RULE` | Automated rule executed |
| `GOOGLE_ADS_RECOMMENDATIONS` | Recommendation manually applied |
| `GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION` | **Auto-applied recommendation** |
| `GOOGLE_ADS_MOBILE_APP` | Mobile app change |
| `GOOGLE_INTERNAL` | Google internal system change |

**Key BrightMatter usage**: Filter for `client_type = GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION` to detect auto-applied recommendations. Filter for `client_type = GOOGLE_INTERNAL` to detect Google system changes.

### Constraints
- **30-day lookback window** — changes older than 30 days are not accessible
- **LIMIT required** — max 10,000 rows per query; paginate by `change_date_time` for more
- **3-minute delay** — changes take up to 3 minutes to appear in results
- **Before/after values**: UPDATE operations include both old and new values; CREATE operations include only new values

### Example Query
```sql
SELECT
  change_event.change_date_time,
  change_event.user_email,
  change_event.client_type,
  change_event.change_resource_type,
  change_event.resource_change_operation,
  change_event.changed_fields,
  change_event.old_resource,
  change_event.new_resource
FROM change_event
WHERE change_event.change_date_time >= '2026-04-01'
  AND change_event.change_date_time <= '2026-04-29'
ORDER BY change_event.change_date_time DESC
LIMIT 10000
```

### ChangeStatus Resource (Lighter Alternative)
The `change_status` resource provides a simpler view of what changed without old/new values. Lower latency but less detail. Useful for quick "did anything change?" checks.

---

## PMax Reporting

### Available Reporting Dimensions

Performance Max uses a different structure — no `ad_group` or `ad_group_ad` resources. Instead:

| Level | Resource | Key Data |
|-------|----------|----------|
| Campaign | `campaign` | Overall PMax campaign performance |
| Channel breakdown | `campaign` + `segments.advertising_channel_sub_type` | Performance by channel (Search, Display, YouTube, etc.) |
| Placements | `performance_max_placement_view` | Where ads appeared |
| Asset group | `asset_group` | Asset group-level performance, ad strength |
| Asset | `asset_group_asset` | Individual asset performance ratings |
| Top combinations | `asset_group_top_combination_view` | Best-performing asset combinations |
| Retail/Shopping | `shopping_performance_view`, `shopping_product` | Product-level performance |
| Product groups | `asset_group_product_group_view` | Product group tree performance |
| Search terms | `campaign_search_term_view` | Search terms triggering PMax ads |
| Location | `location_view` | Geographic performance |

### Channel-Level Breakdown
PMax campaigns can be segmented by channel using `segments.advertising_channel_sub_type`:
- SEARCH
- DISPLAY
- SHOPPING
- VIDEO (YouTube)

This is available at both campaign and asset group levels.

### Limitations
- No keyword-level bidding or reporting (PMax is fully automated)
- Auction Insights available but limited to Search and Shopping segments
- Asset performance ratings are categorical (LOW, GOOD, BEST), not numerical
- No creative-level CTR/CVR reporting (only asset performance labels)
- Limited search term visibility compared to Search campaigns

### Example Query — PMax Campaign by Channel
```sql
SELECT
  campaign.id,
  campaign.name,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.cost_micros,
  segments.date
FROM campaign
WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
  AND segments.date DURING LAST_30_DAYS
```

---

## Quality Score Data

### Available Fields (from `keyword_view` / `ad_group_criterion`)

**Current Quality Score:**
| Field | Type | Description |
|-------|------|-------------|
| `ad_group_criterion.quality_info.quality_score` | INT32 | Overall QS (1–10) |
| `ad_group_criterion.quality_info.creative_relevance` | ENUM | Ad relevance (BELOW_AVERAGE, AVERAGE, ABOVE_AVERAGE) |
| `ad_group_criterion.quality_info.post_click_quality_score` | ENUM | Landing page experience |
| `ad_group_criterion.quality_info.search_predicted_ctr` | ENUM | Expected CTR |

**Historical Quality Score (via `keyword_view` metrics):**
| Field | Description |
|-------|-------------|
| `metrics.historical_quality_score` | Historical QS when segmented by date |
| `metrics.historical_landing_page_quality_score` | Historical landing page component |
| `metrics.historical_creative_quality_score` | Historical ad relevance component |
| `metrics.historical_search_predicted_ctr` | Historical expected CTR component |

### Key Notes for BrightMatter
- **Historical QS is available** when using `segments.date` — this enables tracking QS changes over time
- QS is only computed for keywords with sufficient impression volume
- QS components are ENUMs (BELOW_AVERAGE, AVERAGE, ABOVE_AVERAGE), not numerical scores
- QS updates lag behind actual changes by 2–4 weeks
- Only applicable to Search campaigns (not Shopping, PMax, Display)

### Example Query — QS Trend Tracking
```sql
SELECT
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type,
  metrics.historical_quality_score,
  metrics.historical_landing_page_quality_score,
  metrics.historical_creative_quality_score,
  metrics.historical_search_predicted_ctr,
  metrics.impressions,
  segments.date
FROM keyword_view
WHERE segments.date DURING LAST_90_DAYS
  AND campaign.status = 'ENABLED'
  AND ad_group.status = 'ENABLED'
  AND ad_group_criterion.status = 'ENABLED'
  AND metrics.impressions > 0
```

---

## Auction Insights

### Available Data via API
Auction Insights metrics are accessible via the `keyword_view` resource using the `segments.auction_insight_domain` segment:

| Metric | Description |
|--------|-------------|
| `metrics.auction_insight_search_impression_share` | Competitor's impression share |
| `metrics.auction_insight_search_overlap_rate` | How often competitor shows when you do |
| `metrics.auction_insight_search_outranking_share` | How often you outrank competitor |
| `metrics.auction_insight_search_position_above_rate` | How often competitor is above you |
| `metrics.auction_insight_search_top_impression_percentage` | Competitor's top-of-page rate |
| `metrics.auction_insight_search_absolute_top_impression_percentage` | Competitor's absolute top rate |

### Granularity
- Available at keyword, ad group, and campaign level
- Can be segmented by date for trend analysis
- Only returns data when impression share ≥ 10%
- Search campaigns provide all 6 metrics; Shopping/PMax provide 3 (impression share, overlap rate, outranking share)

### Historical Depth
- Available for the same historical depth as other performance data (typically up to 2+ years)
- Segmentable by `segments.date` for daily granularity

### Limitations
- Competitor domains are anonymized in some cases
- Small accounts or low-traffic keywords may not have enough data
- As of April 2025, double-serving policy allows multiple ads from same advertiser, changing metric interpretation
- PMax auction insights are limited to Search and Shopping channel segments

### Example Query — Competitive Monitoring
```sql
SELECT
  campaign.name,
  segments.auction_insight_domain,
  segments.date,
  metrics.auction_insight_search_impression_share,
  metrics.auction_insight_search_overlap_rate,
  metrics.auction_insight_search_outranking_share,
  metrics.auction_insight_search_position_above_rate
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
  AND campaign.status = 'ENABLED'
  AND ad_group.status = 'ENABLED'
```

---

## MCC Account Traversal

### How to Iterate 500 Accounts from a Single MCC

**Step 1: List Accessible Customers**
```python
customer_service = client.get_service("CustomerService")
response = customer_service.list_accessible_customers()
# Returns resource names like "customers/1234567890"
```
This returns only accounts where the authenticated user has direct admin access — not the full hierarchy.

**Step 2: Get Full Account Hierarchy**
```sql
SELECT
  customer_client.client_customer,
  customer_client.level,
  customer_client.manager,
  customer_client.descriptive_name,
  customer_client.id,
  customer_client.status
FROM customer_client
WHERE customer_client.status = 'ENABLED'
```
Run this against each accessible MCC to discover all child accounts recursively.

**Step 3: Query Each Account**
For each child account, set `customer_id` to the child's ID and execute queries. The `login-customer-id` header should be set to the MCC account ID.

### Batch Patterns for 500 Accounts

**Sequential approach (simplest):**
```python
for customer_id in all_account_ids:
    response = ga_service.search_stream(
        customer_id=customer_id,
        query=query
    )
    for batch in response:
        process(batch)
```

**Parallel approach (recommended for throughput):**
- Use Python `concurrent.futures.ThreadPoolExecutor` with 10–20 threads
- Each thread handles one account at a time
- Respects API rate limits while maximizing throughput

**Key considerations:**
- Each account query counts as 1 API operation against daily quota
- `SearchStream` is preferred over `Search` for large result sets (counts as 1 operation regardless of result size)
- Paginated `Search` requests: first page counts as 1 operation; subsequent pages are free
- Cancelled accounts won't appear in `customer_client` but can be identified by comparing `customer_client_link` (ACTIVE) vs. `customer_client` (ENABLED)

---

## Rate Limits & Feasibility

### Quota Summary

| Access Level | Daily Operations | Cost |
|--------------|-----------------|------|
| Explorer (test) | 2,880/day (production), 15,000/day (test) | Free |
| Basic | 15,000/day | Free |
| Standard | Unlimited (most services) | Free |

### Feasibility Analysis for 500 Accounts Daily

**Minimum daily queries per account (for core pattern detection):**
| Query | Operations |
|-------|-----------|
| Campaign performance (last 30 days) | 1 |
| Keyword QS & performance | 1 |
| Auction Insights | 1 |
| Change History | 1 |
| Conversion action config | 1 |
| Shopping/PMax performance (if applicable) | 1 |
| **Total per account** | **~6** |

**Total daily operations: 500 accounts × 6 queries = 3,000 operations**

| Access Level | Feasible? | Headroom |
|--------------|-----------|----------|
| Explorer | NO — 2,880 limit too low | -120 |
| Basic | YES — 15,000 limit | 12,000 ops remaining (80% headroom) |
| Standard | YES — unlimited | Full headroom |

**Recommendation**: Apply for **Basic Access** immediately (sufficient for BrightMatter). Apply for **Standard Access** once the system is production-ready and query volume grows.

### Additional Constraints
- **gRPC message size**: 64 MB max response — use `SearchStream` and limit `SELECT` fields
- **IN clause**: Max 20,000 items
- **Mutate**: 10,000 operations per request (not relevant for read-only monitoring)
- **No per-second rate limit on SearchStream** — but don't blast requests; use reasonable concurrency (10–20 parallel)

### Recommended Batch Strategy
1. Run full data pull during off-peak hours (2–6 AM account timezone)
2. Use `SearchStream` for all queries (1 operation per query regardless of result size)
3. Parallelize with 10–20 threads across accounts
4. Expected total runtime: 500 accounts × 6 queries × ~2 sec/query ÷ 15 threads ≈ **~7 minutes**
5. Store results in a data warehouse (Snowflake, BigQuery) for cross-account analysis
6. For real-time monitoring, poll high-priority accounts more frequently (every 4 hours)

---

## Available Metrics & Segments

### Key Metrics for Pattern Detection

**Core Performance Metrics:**
| Metric | Field | Use Case |
|--------|-------|----------|
| Impressions | `metrics.impressions` | Demand tracking, seasonality |
| Clicks | `metrics.clicks` | Traffic monitoring |
| Cost | `metrics.cost_micros` | Spend tracking (in micros, divide by 1M) |
| Conversions | `metrics.conversions` | Conversion tracking health |
| Conv. Value | `metrics.conversions_value` | Revenue tracking |
| CTR | `metrics.ctr` | Ad relevance / SERP changes |
| Avg. CPC | `metrics.average_cpc` | CPC inflation detection |
| Conv. Rate | `metrics.conversions_from_interactions_rate` | CVR anomaly detection |
| All Conv. | `metrics.all_conversions` | Includes secondary conv. actions |

**Impression Share Metrics (competitive health):**
| Metric | Field |
|--------|-------|
| Search IS | `metrics.search_impression_share` |
| IS Lost (Budget) | `metrics.search_budget_lost_impression_share` |
| IS Lost (Rank) | `metrics.search_rank_lost_impression_share` |
| Top IS | `metrics.search_top_impression_share` |
| Abs. Top IS | `metrics.search_absolute_top_impression_share` |

**Quality Score Metrics:**
| Metric | Field |
|--------|-------|
| QS | `metrics.historical_quality_score` |
| Landing Page QS | `metrics.historical_landing_page_quality_score` |
| Ad Relevance QS | `metrics.historical_creative_quality_score` |
| Expected CTR | `metrics.historical_search_predicted_ctr` |

**Auction Insights Metrics:**
| Metric | Field |
|--------|-------|
| Competitor IS | `metrics.auction_insight_search_impression_share` |
| Overlap Rate | `metrics.auction_insight_search_overlap_rate` |
| Outranking Share | `metrics.auction_insight_search_outranking_share` |
| Position Above Rate | `metrics.auction_insight_search_position_above_rate` |
| Top IS | `metrics.auction_insight_search_top_impression_percentage` |
| Abs. Top IS | `metrics.auction_insight_search_absolute_top_impression_percentage` |

**Shopping/E-commerce Metrics:**
| Metric | Field |
|--------|-------|
| Cart Size | `metrics.average_cart_size` |
| AOV | `metrics.average_order_value_micros` |
| COGS | `metrics.cost_of_goods_sold_micros` |
| Gross Profit | `metrics.gross_profit_micros` |
| Cross-sell Revenue | `metrics.cross_sell_revenue_micros` |

**Cross-device & Engagement:**
| Metric | Field |
|--------|-------|
| Cross-device Conv. | `metrics.cross_device_conversions` |
| Bounce Rate | `metrics.bounce_rate` |
| Avg. Page Views | `metrics.average_page_views` |
| Avg. Time on Site | `metrics.average_time_on_site` |

### Key Segments for Pattern Detection

| Segment | Field | Use Case |
|---------|-------|----------|
| Date | `segments.date` | Time-series analysis, trend detection |
| Day of Week | `segments.day_of_week` | Weekly pattern analysis |
| Month | `segments.month` | Monthly aggregation |
| Quarter | `segments.quarter` | Quarterly benchmarking |
| Year | `segments.year` | YoY comparison |
| Device | `segments.device` | Device-specific anomalies (iOS impact) |
| Ad Network | `segments.ad_network_type` | Search vs. Display vs. Partners |
| Auction Domain | `segments.auction_insight_domain` | Competitive analysis |
| Conversion Action | `segments.conversion_action` | Conversion-specific tracking |
| Conversion Action Name | `segments.conversion_action_name` | Human-readable conversion identification |
| Conv. Category | `segments.conversion_action_category` | Conversion type grouping |
| Conv. Lag Bucket | `segments.conversion_lag_bucket` | Attribution delay analysis |
| Click Type | `segments.click_type` | Sitelink, headline, etc. |
| Slot | `segments.slot` | Ad position analysis |
| New vs. Returning | `segments.new_versus_returning_customers` | Audience composition |

---

## Python Client Setup

### Installation
```bash
pip install google-ads
```
Requires Python 3.9+.

### Authentication Configuration
Create a `google-ads.yaml` file:
```yaml
developer_token: INSERT_DEVELOPER_TOKEN
client_id: INSERT_OAUTH2_CLIENT_ID
client_secret: INSERT_OAUTH2_CLIENT_SECRET
refresh_token: INSERT_REFRESH_TOKEN
login_customer_id: INSERT_MCC_CUSTOMER_ID  # 10-digit MCC ID, no dashes
```

### Client Initialization
```python
from google.ads.googleads.client import GoogleAdsClient

client = GoogleAdsClient.load_from_storage("google-ads.yaml")
```

### Query Execution with SearchStream
```python
def query_account(client, customer_id, query):
    ga_service = client.get_service("GoogleAdsService")
    response = ga_service.search_stream(
        customer_id=str(customer_id),
        query=query
    )
    rows = []
    for batch in response:
        for row in batch.results:
            rows.append(row)
    return rows
```

### MCC Multi-Account Pattern
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def pull_all_accounts(client, account_ids, query, max_workers=15):
    results = {}

    def fetch(cid):
        try:
            return cid, query_account(client, cid, query)
        except Exception as e:
            return cid, e

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, cid): cid for cid in account_ids}
        for future in as_completed(futures):
            cid, data = future.result()
            results[cid] = data

    return results
```

### Error Handling
```python
from google.ads.googleads.errors import GoogleAdsException

try:
    response = ga_service.search_stream(
        customer_id=customer_id, query=query
    )
    for batch in response:
        for row in batch.results:
            process(row)
except GoogleAdsException as ex:
    for error in ex.failure.errors:
        print(f"Error: {error.error_code}: {error.message}")
    print(f"Request ID: {ex.request_id}")
```

### Key Tips
- `SearchStream` is preferred over `Search` for large result sets — single API operation regardless of result size
- The `ga_service` and streaming iterator must remain in the same scope to avoid gRPC channel garbage collection
- Use `client.get_service("GoogleAdsService")` — don't cache service objects across threads
- Costs are in **micros** (1,000,000 micros = $1) — divide by 1,000,000 for dollar amounts
- Use `login_customer_id` in config to specify the MCC when querying child accounts

---

## Mapping: Pattern Domains → API Resources

### For Each of the 12 Causal Chains: Required API Resources

| # | Pattern Domain | Primary API Resources | Key Fields |
|---|---------------|----------------------|------------|
| 1 | Tracking Breaks | `campaign`, `conversion_action` | `metrics.conversions`, `metrics.clicks`, `conversion_action.status`, `segments.date` |
| 2 | Landing Page Changes | `keyword_view`, `ad_group_criterion` | `metrics.historical_landing_page_quality_score`, `metrics.conversions_from_interactions_rate`, `ad_group_criterion.quality_info.*` |
| 3 | CPC Inflation | `campaign`, `keyword_view` | `metrics.average_cpc`, `metrics.search_impression_share`, `metrics.search_budget_lost_impression_share`, `segments.date` |
| 4 | Competitor Changes | `keyword_view` (with `auction_insight_domain` segment) | `metrics.auction_insight_search_*`, `segments.auction_insight_domain`, `segments.date` |
| 5 | Platform Changes | `campaign`, `change_event` | All performance metrics + `change_event.client_type` (to confirm no changes made) |
| 6 | Seasonality | `campaign` | `metrics.impressions`, `metrics.clicks`, `metrics.conversions`, `segments.date` (YoY comparison) |
| 7 | Privacy/Tracking | `campaign`, `conversion_action` | `metrics.conversions`, `metrics.all_conversions`, `metrics.cross_device_conversions`, `segments.device` |
| 8 | Search Demand | `campaign`, `keyword_view` | `metrics.impressions`, `metrics.search_impression_share`, `segments.date` (cross-ref with Google Trends API) |
| 9 | Product/Pricing | `shopping_performance_view`, `shopping_product`, `asset_group_product_group_view` | Product-level metrics, `metrics.average_order_value_micros`, feed data |
| 10 | Cross-Channel | `campaign` (brand keywords) | `metrics.impressions` for brand campaigns, `segments.date` (cross-ref with CRM/Meta data) |
| 11 | Auto-Applied | `change_event` | `change_event.client_type = GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION`, `change_event.changed_fields`, `change_event.old_resource`, `change_event.new_resource` |
| 12 | Conv. Definition | `conversion_action`, `change_event` | `conversion_action.attribution_model_settings`, `conversion_action.counting_type`, `conversion_action.status`, `change_event.change_resource_type` |

### Data NOT Available via API (External Sources Needed)

| Need | Source |
|------|--------|
| Google Trends search volume | Google Trends API (separate) |
| Core Web Vitals / page speed | PageSpeed Insights API, CrUX API |
| Meta/social ad spend data | Meta Marketing API, CRM data |
| CRM conversion verification | Client's CRM API |
| Merchant Center feed changes | Google Merchant Center API (Content API for Shopping) |
| Competitor ad copy / spend | SEMrush, SpyFu (third-party) |
| AI Overview presence on SERPs | Adthena, Seer Interactive (third-party) |
| Platform change announcements | Search Engine Land RSS, Google Ads Blog |

### Recommended External API Integrations for BrightMatter

| Priority | API | Purpose |
|----------|-----|---------|
| P0 | Google Ads API | Core data source |
| P0 | Google Trends API | Search demand shift detection |
| P1 | PageSpeed Insights API | Landing page health monitoring |
| P1 | Google Merchant Center API | Product/pricing/inventory changes |
| P2 | CRM APIs (HubSpot, Salesforce) | Conversion verification (tracking break vs. real decline) |
| P2 | Meta Marketing API | Cross-channel spillover correlation |
| P3 | SEMrush/SpyFu API | Competitive intelligence enrichment |

---

## API Version Strategy

The Google Ads API releases new versions regularly and deprecates old ones. As of April 2026:

- **Current latest**: v24
- **Recommended for new development**: Latest stable version
- **Version lifecycle**: Each version is supported for ~12 months after release
- **Migration**: Update client library version and change version in service calls

For BrightMatter, pin to a specific version for stability but plan quarterly version upgrades to access new features and maintain support.

---

## Summary: API Readiness for BrightMatter

| Capability | API Coverage | Notes |
|------------|-------------|-------|
| Performance metrics | Complete | All standard metrics available |
| Quality Score tracking | Complete | Historical QS with date segmentation |
| Auction Insights | Good | Available via keyword_view with auction_insight_domain segment |
| Change history / auto-applied detection | Excellent | Full change audit trail with actor attribution |
| PMax reporting | Good | Channel-level breakdowns, product data available |
| MCC account traversal | Complete | Recursive hierarchy traversal supported |
| Rate limits for 500 accounts | Feasible | Basic Access (15K ops/day) sufficient; Standard recommended |
| Conversion action audit | Complete | Full configuration queryable |
| Cross-account pattern detection | Requires BrightMatter logic | API provides per-account data; cross-account analysis is BrightMatter's value-add |
