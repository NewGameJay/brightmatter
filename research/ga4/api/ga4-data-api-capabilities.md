# GA4 Data API: Capabilities, Scope Rules & Quotas

*Everything needed to query GA4 correctly. Getting this wrong produces silent errors — wrong numbers that look plausible.*

---

## API Overview

- **Endpoint:** `https://analyticsdata.googleapis.com/v1beta/properties/{propertyId}:runReport`
- **Method:** POST with JSON body
- **Auth:** OAuth 2.0 with `analytics.readonly` scope
- **Python client:** `google-analytics-data` package (`BetaAnalyticsDataClient`)
- **Admin API (for discovery):** `analyticsadmin.googleapis.com/v1beta/accountSummaries`

## Request Structure

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange, FilterExpression
)

client = BetaAnalyticsDataClient()
request = RunReportRequest(
    property=f"properties/{property_id}",
    dimensions=[
        Dimension(name="landingPage"),
        Dimension(name="deviceCategory"),
        Dimension(name="date"),
    ],
    metrics=[
        Metric(name="sessions"),
        Metric(name="engagedSessions"),
        Metric(name="engagementRate"),
        Metric(name="bounceRate"),
        Metric(name="averageSessionDuration"),
        Metric(name="conversions"),
        Metric(name="totalRevenue"),
    ],
    date_ranges=[DateRange(start_date="60daysAgo", end_date="today")],
    limit=10000,
)
response = client.run_report(request)
```

## Scope Rules (CRITICAL)

GA4 has five scopes. Mixing them produces wrong numbers silently.

| Scope | What it covers | Example dimensions | Example metrics |
|-------|---------------|-------------------|-----------------|
| Event | Single interaction | eventName, pagePath | eventCount, eventValue |
| Session | Group of events in one visit | landingPage, sessionSource, sessionMedium | sessions, engagedSessions, bounceRate |
| User | Across all sessions | firstUserSource, country, deviceCategory | activeUsers, newUsers |
| Item | Ecommerce product | itemName, itemCategory, itemBrand | itemRevenue, itemsPurchased |
| Ad | Advertising data | googleAdsCampaignName, googleAdsAdGroupName | advertiserAdCost, advertiserAdClicks |

**The trap:** A user-scoped dimension paired with an event-scoped metric returns unexpected totals or blank cells. A session-scoped dimension with an item-scoped metric produces meaningless joins.

**The rule for BrightMatter:** Landing page analysis = session scope. Funnel analysis = event scope. User acquisition = user scope. Never mix scopes in one query unless you understand the aggregation behavior.

**Cardinality:** When a dimension exceeds the daily unique-value limit, GA4 buckets overflow into an `(other)` row. High-cardinality dimensions like full URLs or user IDs are the usual culprits. For landing page analysis, use `landingPage` (path only) not `landingPagePlusQueryString` to reduce cardinality.

## Quotas

GA4 API quotas are per-property and per-project. Three categories: Core, Realtime, Funnel. BrightMatter uses Core only.

| Quota | Standard (free) | GA360 |
|-------|----------------|-------|
| Tokens per day per property | 25,000 | 250,000 |
| Tokens per hour per property | 5,000 | 50,000 |
| Concurrent requests per property | 10 | 50 |
| Server errors per hour per project | 10 | 50 |

**Token consumption:** Most simple requests cost ~10 tokens. Complex requests (many dimensions, long date ranges, high cardinality) cost more. A 60-day report with 3 dimensions and 7 metrics costs roughly 15-25 tokens.

**For 193 properties at daily ingestion:** ~193 × 15 tokens = ~2,900 tokens/day per property if batched efficiently. Well within the 25,000/day limit IF each property is queried once daily with a single aggregated report.

**The risk:** Running multiple queries per property per day (one for landing pages, one for funnels, one for device splits) multiplies token usage. Combine dimensions in as few requests as possible. Use `batchRunReports` endpoint to combine up to 5 report requests in one API call.

## Key Methods

| Method | Use case |
|--------|----------|
| `runReport` | Standard reporting — landing pages, engagement, conversions |
| `batchRunReports` | Up to 5 reports in one call (saves quota) |
| `runRealtimeReport` | Last 30 minutes of data — NOT useful for BrightMatter |
| `runFunnelReport` | Ecommerce funnel analysis (view→cart→checkout→purchase) |
| `getMetadata` | List all available dimensions/metrics for a property |

## Data Retention

- Default: 14 months (Standard), 50 months (GA360)
- Configurable: can be shortened to 2 months
- BrightMatter should check retention setting per property during discovery

## What GA4 API Does NOT Provide

1. **Raw event-level data** — API provides aggregated reports, not individual events. For event-level data, use BigQuery export (free up to 1M events/day on Standard).
2. **Historical UA data** — GA4 API only returns GA4 data. Universal Analytics data is NOT accessible.
3. **Page speed / Core Web Vitals** — NOT available unless custom events were set up. Use CrUX API instead.
4. **Impression data** — GA4 only records sessions (clicks). No impression tracking.
5. **Offline conversions** — phone calls, in-store visits not tracked unless explicitly imported.
6. **Competitor data** — only your own property's data.

## Joining GA4 to Google Ads

**The join key:** `landingPage` (GA4 session-scoped) ↔ `final_url` (Google Ads campaign/ad configuration).

**URL normalization required:**
- Strip query parameters (utm, gclid, fbclid)
- Strip trailing slashes
- Strip www prefix
- Lowercase
- Handle redirects (GA4 records the final URL after redirect, Google Ads records the configured URL)

**Attribution join:** `sessionGoogleAdsCampaignName` (GA4) ↔ `campaign.name` (Google Ads). This links GA4 sessions to the Google Ads campaign that drove them. But attribution differs — Google Ads uses its own model, GA4 uses data-driven attribution across ALL sources. The numbers won't match exactly. Accept the discrepancy and document it.

## CrUX API (Supplementary — Not GA4)

Chrome User Experience Report provides field page speed data for any URL with sufficient Chrome traffic. No auth beyond an API key. No client instrumentation required.

**Endpoint:** `https://chromeuxreport.googleapis.com/v1/records:queryRecord`

**Request:**
```json
{
  "url": "https://www.example.com/landing-page",
  "formFactor": "PHONE",
  "metrics": ["largest_contentful_paint", "cumulative_layout_shift", "interaction_to_next_paint"]
}
```

**Thresholds:**
| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| LCP | ≤2.5s | 2.5-4.0s | >4.0s |
| CLS | ≤0.1 | 0.1-0.25 | >0.25 |
| INP | ≤200ms | 200-500ms | >500ms |

**Coverage:** Any URL with sufficient Chrome traffic (typically >1,000 page loads in 28-day window). Covers all 193 URL'd accounts without any permission grants.
