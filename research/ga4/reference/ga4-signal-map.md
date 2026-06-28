# GA4 Signal Map: What to Ingest, Ranked by BrightMatter Impact

*Every GA4 signal organized by ingestion priority. Focus: what improves BrightMatter's existing predictions and confidence levels.*

---

## Ingestion Tier 1: Ingest First (highest BrightMatter impact)

### 1.1 Landing Page Engagement (session-scoped, per date, per device)

**Dimensions:** landingPage, deviceCategory, date
**Metrics:** sessions, engagedSessions, engagementRate, bounceRate, averageSessionDuration, sessionConversionRate, keyEvents, totalRevenue
**Query:** One runReport per property per day

**Why Tier 1:** Directly fills the largest confidence gap in BrightMatter's Google Ads signals. Every CVR drop and CPA spike signal says "can't rule out landing page quality." This data resolves that.

**BrightMatter integration points:**
- CVR drop signal → check engagement rate on the landing page → upgrade SUGGESTIVE to LIKELY/CONFIRMED
- CPA spike signal → check bounce rate on paid landing pages → narrow diagnosis
- Device mobile drag signal → compare mobile vs desktop engagement on same page → confirm UX issue
- Template conditioning: add `landing_page_engagement_state` as an episode attribute

### 1.2 CrUX Page Speed (per URL, per form factor)

**Source:** CrUX API (NOT GA4 — public, no GA4 access needed)
**Data:** LCP, CLS, INP per URL per form factor (mobile/desktop)
**Coverage:** All 193 URL'd accounts

**Why Tier 1:** Fills the QS landing page experience gap. Covers 13× more accounts than GA4. Zero permission requirements.

**BrightMatter integration points:**
- QS low_quality_score signal → check if LCP > 4s → explain the penalty specifically
- Landing page detector: flag pages with "Poor" Core Web Vitals
- Trend detection: page speed degradation over time (CrUX updates monthly)

---

## Ingestion Tier 2: Ingest Second (meaningful but narrower impact)

### 2.1 Ecommerce Funnel Events (ecommerce accounts only)

**Dimensions:** date, landingPage (optional)
**Metrics:** Event counts for: view_item, add_to_cart, begin_checkout, purchase
**Query:** One runReport with eventName dimension filtered to funnel events
**Coverage:** Only accounts with ecommerce tracking implemented (~80-100 of 193)

**Why Tier 2:** Pinpoints WHERE in the conversion funnel a drop occurs. Google Ads sees "conversions dropped." GA4 sees "add-to-cart dropped 20% but checkout-to-purchase was stable."

**BrightMatter integration points:**
- CVR drop on ecommerce campaigns → check which funnel step degraded → specific diagnosis
- Template enrichment: "creative change on ecommerce/performing_well" → check if view_item→add_to_cart rate changed

### 2.2 Traffic Source Quality (session-scoped, Google Ads traffic specifically)

**Dimensions:** sessionGoogleAdsCampaignName, sessionSource, sessionMedium, date
**Metrics:** sessions, engagementRate, bounceRate, sessionConversionRate
**Coverage:** 15 cross-referenced accounts initially, expandable

**Why Tier 2:** Isolates Google Ads-driven session quality from overall site quality. If engagement rate drops only on paid traffic while organic is stable, the issue is ad targeting or message match — not the website.

**BrightMatter integration points:**
- Cross-platform episodes: "Google Ads creative change → GA4 paid bounce rate spiked → CVR dropped"
- Attribution comparison: Google Ads conversion count vs GA4 session conversion rate on same campaigns

---

## Ingestion Tier 3: Ingest Later (supplementary)

### 3.1 Session Duration and Scroll Depth by Page

**Dimensions:** landingPage, date
**Metrics:** averageSessionDuration, userEngagementDuration
**Plus:** scroll event counts if enhanced measurement is enabled

**Why Tier 3:** Secondary diagnostic. Engagement rate already captures the "did they stick around?" signal. Duration and scroll add "how much did they engage?" — useful for content quality assessment but one layer removed from conversion prediction.

### 3.2 New vs Returning Users by Landing Page

**Dimensions:** landingPage, newVsReturning, date
**Metrics:** sessions, conversions

**Why Tier 3:** Helps diagnose audience composition shifts. If a campaign starts attracting more new users (who typically convert at lower rates), CVR drops even though the landing page is fine. Low priority because the Google Ads audience data partially covers this.

### 3.3 Full GA4 Attribution Path (15 cross-referenced accounts)

**Method:** runFunnelReport or Exploration API
**Data:** Multi-touch conversion paths showing all touchpoints

**Why Tier 3:** Valuable for understanding cross-channel attribution but complex to ingest, complex to interpret, and only available on 15 accounts. Phase 4 territory after the simpler signals prove their value.

---

## Signals NOT Worth Ingesting

| Signal | Why Not |
|--------|---------|
| Realtime data | BrightMatter runs daily, not realtime. No use case. |
| User demographics (age, gender) | Low accuracy due to consent/modeling. Doesn't improve templates. |
| Technology details (browser, OS) | Too granular for campaign-level templates. |
| Site search queries | Interesting for content strategy, irrelevant for BrightMatter's action → outcome predictions. |
| Video engagement metrics | Only relevant for YouTube campaigns, which aren't in the current detector set. |
| Custom dimensions | Varies by property. No standardized value across 193 accounts. |

---

## Schema: New DuckDB Tables

### ga4_landing_pages (Tier 1)
```sql
CREATE TABLE ga4_landing_pages (
    ga4_property_id  VARCHAR,
    account_id       VARCHAR,  -- joined from ga4_property_map
    date             DATE,
    landing_page     VARCHAR,
    device           VARCHAR,  -- mobile / desktop / tablet
    sessions         INTEGER,
    engaged_sessions INTEGER,
    engagement_rate  FLOAT,
    bounce_rate      FLOAT,
    avg_session_duration FLOAT,
    session_cvr      FLOAT,
    key_events       INTEGER,
    revenue          FLOAT
);
```

### page_speed (Tier 1 — CrUX)
```sql
CREATE TABLE page_speed (
    url              VARCHAR,
    account_id       VARCHAR,  -- matched from accounts.website_url
    form_factor      VARCHAR,  -- PHONE / DESKTOP
    lcp_ms           FLOAT,
    cls              FLOAT,
    inp_ms           FLOAT,
    lcp_category     VARCHAR,  -- good / needs_improvement / poor
    cls_category     VARCHAR,
    inp_category     VARCHAR,
    fetched_at       TIMESTAMP
);
```

### ga4_funnel_events (Tier 2 — ecommerce only)
```sql
CREATE TABLE ga4_funnel_events (
    ga4_property_id  VARCHAR,
    account_id       VARCHAR,
    date             DATE,
    event_name       VARCHAR,  -- view_item / add_to_cart / begin_checkout / purchase
    event_count      INTEGER,
    landing_page     VARCHAR   -- optional, if segmented by entry page
);
```

---

## Joining GA4 to Google Ads: The URL Normalization Problem

The join key between GA4 and Google Ads is the landing page URL. But URLs are messy:

| Source | URL Format |
|--------|-----------|
| Google Ads `final_url` | `https://www.example.com/product-page` |
| GA4 `landingPage` | `/product-page` (path only, no domain) |
| GA4 `landingPagePlusQueryString` | `/product-page?gclid=abc123&utm_source=google` |
| CrUX | `https://www.example.com/product-page` (full URL) |

**Normalization function:**
```python
def normalize_url(url):
    """Normalize a URL for joining across platforms."""
    from urllib.parse import urlparse, parse_qs, urlencode
    parsed = urlparse(url.lower().rstrip('/'))
    # Strip tracking params
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items()
                    if k not in ('gclid', 'fbclid', 'utm_source', 'utm_medium',
                                 'utm_campaign', 'utm_content', 'utm_term')}
    # Reconstruct
    path = parsed.path.rstrip('/')
    if not path:
        path = '/'
    return path  # For GA4 join, path is sufficient
```

**For BrightMatter:** Join on normalized path. Accept that some joins will miss (redirects, URL rewriting, SPA routing). Track the join hit rate per account — if <50% of Google Ads campaigns match a GA4 landing page, the join is unreliable for that account.
