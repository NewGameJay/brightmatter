# BrightMatter Signal Map: Google Ads Features, Configurations & External Influences

*What to ingest, what to track, and what external signals inform strategy — organized by decision category.*

---

## Part 1: Google Ads Internal Features & Configurations

Everything you can set, change, or measure inside Google Ads. Organized by hierarchy level.

---

### Account Level

**Settings & Configuration**
- Conversion tracking setup (primary vs. secondary goals, conversion windows, attribution models)
- Cross-account conversion tracking (MCC-level shared conversion actions)
- Auto-tagging (GCLID appending for GA4/CRM matching)
- Linked accounts (Google Merchant Center, GA4, YouTube, Search Console, Salesforce/CRM, Firebase)
- Customer data / audience lists (Customer Match uploads, website visitors, app users)
- Brand safety settings (content exclusions, placement exclusions, topic exclusions)
- IP exclusions
- Account-level automated extensions
- Manager account (MCC) structure and hierarchy

**Metrics Available (Account Level)**
- Account-wide spend, conversions, conversion value, CPA, ROAS
- Change history (every mutation logged with timestamp and user)
- Recommendations and optimization score
- Account-level Quality Score distribution

---

### Campaign Level

**Campaign Types**
- Search (standard keyword-targeted text ads on Google Search)
- Performance Max (AI-driven cross-channel: Search, Display, YouTube, Gmail, Maps, Discover)
- Shopping (Standard Shopping with product feed from Merchant Center)
- Display (banner/image ads across Google Display Network)
- Video (YouTube — in-stream, bumper, in-feed, Shorts)
- Demand Gen (Discovery/Gmail/YouTube Shorts feed-based)
- App (Universal App campaigns for installs/engagement)
- Hotel (for hotel advertisers, Percent CPC or commission bidding)
- Local (deprecated, folded into PMax)
- Smart (simplified campaigns for small businesses, limited API access)

**Bidding Strategies**

*Smart Bidding (automated, auction-time):*
- Target CPA (maximize conversions at a target cost-per-acquisition)
- Target ROAS (maximize conversion value at a target return-on-ad-spend)
- Maximize Conversions (spend full budget to get the most conversions)
- Maximize Conversion Value (spend full budget to get the highest conversion value)

*Other Automated:*
- Maximize Clicks (spend budget for the most clicks)
- Target Impression Share (bid to appear at top of page, absolute top, or anywhere)

*Manual:*
- Manual CPC (set your own bids at keyword/ad group level)
- Enhanced CPC — deprecated March 2025, reverted to Manual CPC

*Portfolio Strategies:*
- Any Smart Bidding strategy shared across multiple campaigns
- Shared budget allocation across portfolio campaigns

**Budget Settings**
- Daily budget (average spend per day; can overspend up to 2x on any given day)
- Campaign total budget (for campaigns with fixed start/end dates)
- Shared budgets (single budget across multiple campaigns)
- Budget delivery method (standard pacing throughout the day)

**Network Settings**
- Google Search (core search results)
- Search Partners (third-party search sites — often lower quality)
- Google Display Network (for Search campaigns, opt-in)
- YouTube and Video Partners (for video campaigns)
- Note: PMax campaigns automatically serve across all networks with no manual control

**Targeting (Campaign Level)**
- Geographic targeting (countries, regions, cities, radius, postal codes)
- Location options (presence in location vs. interest in location — critical distinction)
- Language targeting
- Ad schedule (day and time parting — which hours/days ads run)
- Device targeting (desktop, mobile, tablet — bid adjustments)
- Audience signals (for PMax: first-party lists, custom segments, in-market, affinity)
- Content exclusions (for Display/Video: sensitive categories, content types)
- Placement exclusions (specific sites, apps, YouTube channels to block)
- Brand inclusions/exclusions (for PMax: control brand term matching)
- URL expansion settings (for PMax: allow/restrict which landing pages Google can use)

**Campaign-Level Settings**
- Start/end dates
- Ad rotation (optimize for clicks/conversions vs. rotate indefinitely)
- Campaign priority (for Shopping: 0, 1, or 2 — higher takes precedence)
- Feed labels (for Shopping: which Merchant Center feed to use)
- Dynamic Search Ad settings (which pages to target automatically)
- AI Max settings (enable/disable AI-driven keyword expansion, creative generation, URL expansion)
- Political advertising declarations (EU requirement)
- New customer acquisition settings (bid differently for new vs. returning customers)

---

### Ad Group Level

**Structure**
- Ad group type (standard, dynamic, hotel listing)
- Default bid (CPC bid for the ad group, overridden at keyword level)
- Target CPA/ROAS override (ad-group level overrides of campaign bidding targets)
- Status (enabled, paused, removed)

**Targeting (Ad Group Level)**
- Targeting settings per criterion type (Targeting vs. Observation mode)
  - Targeting mode: only show ads to users matching criteria
  - Observation mode: show to everyone but bid differently for matching users
- Audience segments (remarketing lists, similar audiences, in-market, custom intent)
- Demographics (age, gender, parental status, household income)
- Topics (for Display: topical categories of sites/content)
- Placements (for Display: specific websites, apps, YouTube channels)
- Keywords (for Search: the core targeting mechanism)

---

### Keyword Level

**Match Types**
- Exact match: query must match keyword meaning (includes close variants in 2026)
- Phrase match: query must include keyword meaning in order (absorbed modified broad)
- Broad match: AI-driven intent matching — now leverages Smart Bidding signals

**Keyword Settings**
- Keyword bid (overrides ad group default)
- Keyword status (enabled, paused, removed)
- Final URL (keyword-level URL override)

**Negative Keywords**
- Negative exact, phrase, and broad match
- Negative keyword lists (shared across campaigns)
- Campaign-level negatives vs. ad-group-level negatives
- PMax negative keywords (now supported at campaign level)

**Quality Score Components (Keyword Level)**
- Overall Quality Score (1-10 diagnostic, not used directly in auction)
- Expected CTR (Above Average / Average / Below Average)
- Ad Relevance (Above Average / Average / Below Average)
- Landing Page Experience (Above Average / Average / Below Average)
- Historical Quality Score (point-in-time snapshots)

---

### Ad / Creative Level

**Search Ads**
- Responsive Search Ads (RSAs): up to 15 headlines, 4 descriptions — Google's AI assembles combinations
- Headline pinning (force specific headlines into positions 1, 2, or 3)
- Description pinning
- Display path (vanity URL paths — 2 fields, 15 chars each)
- Final URL
- Mobile final URL
- Tracking template and custom parameters
- Ad Strength rating (Poor, Average, Good, Excellent)
- Dynamic keyword insertion ({KeyWord:default})
- IF functions (customize text based on device, audience, etc.)
- Countdown timers
- Location insertion

**Display / Video Ads**
- Responsive Display Ads (images, logos, headlines, descriptions, videos)
- Image ads (uploaded static creatives)
- Video ads (YouTube creative: in-stream, bumper, in-feed, Shorts)
- HTML5 ads

**PMax Asset Groups**
- Up to 20 images, 5 videos, 15 headlines, 5 long headlines, 5 descriptions per asset group
- Asset group-level audience signals
- Asset group-level search themes (up to 25 per group)
- Asset group-level landing page / final URL settings
- Individual asset performance labels (Best, Good, Low, Learning)

**Ad Extensions / Assets**
- Sitelinks (additional links below the ad)
- Callouts (short text highlights)
- Structured snippets (header + list values)
- Call extensions (phone number)
- Location extensions (linked from Google Business Profile)
- Price extensions (product/service + price cards)
- Promotion extensions (sale/offer callouts)
- Image extensions (supplementary images)
- Lead form extensions (in-ad form submission)
- App extensions (link to app store)
- Business name and logo

---

### Shopping / Product Feed Level

**Merchant Center Feed Attributes**
- Product title, description, brand, GTIN, MPN
- Product category (Google taxonomy)
- Product type (custom taxonomy)
- Custom labels (0–4: custom segmentation for bidding/reporting)
- Price, sale price, availability
- Images (main + additional)
- Shipping, tax, return policy
- Product condition (new, refurbished, used)

**Shopping-Specific Campaign Settings**
- Feed filter (which products to include)
- Product groups and subdivisions (for bidding at product level)
- Listing groups (PMax equivalent of product groups)
- Local inventory ads (for physical stores with local stock)

---

### Reporting Dimensions & Metrics

**Core Performance Metrics**
- Impressions, clicks, cost, CTR, avg CPC
- Conversions, conversion value, conversion rate, CPA, ROAS
- View-through conversions
- All conversions (includes secondary conversion actions)
- Interaction rate (cross-campaign-type engagement metric)
- Invalid clicks and invalid click rate

**Competitive / Diagnostic Metrics**
- Search impression share (% of eligible impressions captured)
- Search budget lost impression share (lost due to budget)
- Search rank lost impression share (lost due to Ad Rank)
- Search absolute top impression share (appeared in position 1)
- Search top impression share (appeared above organic results)
- Display impression share (and corresponding lost metrics)
- Auction Insights (overlap rate, position above rate, outranking share vs. named competitors)

**Conversion Detail**
- Conversion by conversion action (which events are firing)
- Conversion lag (days between click and conversion)
- Conversion path (multi-touch attribution)
- New vs. returning customer conversions

**Segmentation Dimensions**
- Date (day, week, month, quarter, year)
- Device (mobile, desktop, tablet)
- Network (Search, Search Partners, Display, YouTube)
- Click type (headline, sitelink, call, etc.)
- Slot (top, other)
- Hour of day, day of week
- Geographic (country, region, city, metro area)
- Search term (actual query that triggered the ad)
- Landing page URL
- Ad network type
- Conversion source

---

## Part 2: External Signals That Influence Google Ads Strategy

Everything *outside* Google Ads that affects performance, decisions, and what BrightMatter should track.

---

### Landing Page & Website Quality

**Why it matters:** Landing page experience is one of three Quality Score components. It directly affects Ad Rank and CPC. Google's crawlers evaluate page content, and that assessment feeds into auction-time quality calculations.

**What to track:**
- Page load speed (Core Web Vitals: LCP, CLS, INP)
- Mobile usability score
- Bounce rate by landing page (from GA4)
- Conversion rate by landing page
- Time on page / engagement rate
- Content relevance alignment (does the page match the ad promise?)
- Form completion rate (for lead gen)
- Cart completion rate (for ecommerce)

**Sources:** Google PageSpeed Insights API, Google Search Console, GA4, CrUX (Chrome User Experience Report), Lighthouse

---

### SEO & Organic Search

**Why it matters:** SEO and paid search interact directly. Organic rankings affect paid CTR (users see your brand twice), and search query data from organic informs keyword strategy. Strong organic presence for a query may mean you can reduce paid spend; weak organic presence means paid must compensate.

**What to track:**
- Organic ranking positions for target keywords
- Organic CTR by keyword
- Keyword overlap between organic and paid (cannibalization vs. complementary)
- Search Console impression/click data for paid keyword terms
- Featured snippet ownership
- Organic traffic trends (declining organic = may need more paid coverage)
- Domain authority / backlink profile (competitive strength indicator)
- AI search / GEO visibility (increasingly relevant as AI Overviews take search share)

**Sources:** Google Search Console API, Ahrefs / SEMrush / Moz APIs, GA4 organic traffic data, BrightEdge, Similarweb

---

### Competitive Intelligence

**Why it matters:** Auction Insights shows you who you're competing against, but it doesn't show their strategy. Competitor ad copy, landing pages, offer positioning, and spending patterns directly affect your CPA and impression share.

**What to track:**
- Competitor ad copy (headlines, descriptions, extensions, offers)
- Competitor landing page URLs and messaging
- New competitor entries / exits from your keyword auctions
- Competitor pricing (for Shopping: price competitiveness index)
- Auction Insights trends over time (are specific competitors gaining share?)
- Competitor creative refresh frequency
- Share of voice by competitor

**Sources:** Google Ads Auction Insights, SEMrush / SpyFu / iSpionage for ad copy monitoring, Prisync / Competera for pricing intelligence, Meta Ad Library (cross-channel creative intelligence)

---

### Seasonality & Market Trends

**Why it matters:** Performance fluctuations are often seasonal, not account-level problems. Recognizing this prevents over-optimizing in response to natural cycles.

**What to track:**
- Google Trends data for core keywords (search volume changes)
- Year-over-year performance comparisons (same period last year)
- Industry-specific seasonal calendars (Black Friday, back-to-school, tax season, etc.)
- Macroeconomic indicators (consumer confidence, unemployment, inflation — affects conversion rates)
- Weather patterns (for relevant verticals: HVAC, travel, seasonal products)
- Cultural events and holidays (by geography)
- Platform-level changes (Google algorithm updates, new ad formats, policy changes)

**Sources:** Google Trends API, Google Ads Keyword Planner (search volume forecasts), BLS economic data, industry benchmark reports (WordStream, LocaliQ, Tinuiti, Merkle quarterly reports)

---

### CRM & First-Party Data

**Why it matters:** Google's algorithms optimize for whatever conversion signal you give them. The quality of that signal determines whether Smart Bidding optimizes for revenue or for junk leads. Offline conversion data and CRM integration are the highest-leverage external inputs.

**What to track:**
- Lead-to-customer conversion rate by campaign/keyword
- Revenue per lead by acquisition source
- Customer lifetime value by acquisition source
- Pipeline stage progression (for B2B: MQL → SQL → Opportunity → Won)
- Offline conversion imports (feeding CRM-qualified events back to Google Ads)
- Customer Match list freshness and match rates
- Churn rate by acquisition source
- Return/refund rate by campaign (for ecommerce)

**Sources:** CRM systems (HubSpot, Salesforce, Pipedrive), Google Ads offline conversion import, Enhanced Conversions, Customer Match API

---

### Attribution & Cross-Channel Performance

**Why it matters:** Google Ads attributes conversions using its own models, which systematically over-credit Google. Decisions based solely on Google's attribution lead to over-investment in Google at the expense of other channels (or under-investment when Google is actually assisting).

**What to track:**
- Cross-channel attribution (multi-touch: first click, last click, linear, time decay, data-driven)
- Assisted conversions (Google campaigns that touched the journey but weren't last click)
- Channel interaction paths (did the user see a Meta ad first, then search on Google?)
- Blended ROAS / MER (total revenue / total marketing spend)
- Incrementality testing results (did the Google campaign actually cause the conversion?)
- Halo effects (does paid search lift organic CTR? does brand search lift non-brand conversion?)

**Sources:** GA4 attribution reports, Northbeam / Triple Whale / Rockerbox / Measured for cross-channel attribution, Google Ads conversion path reports, geographic incrementality tests

---

### Product & Pricing Data

**Why it matters (ecommerce):** Product availability, pricing, reviews, and feed quality directly affect Shopping and PMax campaign performance. A stockout kills ROAS. A price increase tanks conversion rate. These happen outside Google Ads but show up as performance changes inside it.

**What to track:**
- Product availability / stockout status
- Price changes and competitive pricing position
- Product review count and average rating
- Shipping speed and cost (free shipping threshold)
- Product page content quality (descriptions, images, structured data)
- Promotional calendar (what's on sale, when, where)
- New product launches and seasonal assortment changes

**Sources:** Shopify / WooCommerce / BigCommerce APIs, Google Merchant Center diagnostics, product review platforms (Yotpo, Judge.me, Stamped), competitor pricing tools

---

### Platform & Policy Changes

**Why it matters:** Google changes the rules regularly. New features, deprecated features, policy enforcement, and algorithm updates create performance shifts that have nothing to do with your account management.

**What to track:**
- Google Ads product announcements (new campaign types, feature launches)
- Bidding algorithm changes (Smart Bidding model updates)
- Policy enforcement changes (disapprovals, account suspensions, restricted categories)
- Tracking/privacy changes (Consent Mode v2, cookie deprecation, iOS/ATT impact)
- API version changes and deprecations
- Match type behavior changes (broad match expansion, close variants)
- SERP layout changes (more/fewer ads, AI Overviews pushing ads down)

**Sources:** Google Ads developer blog, Google Ads Help Center change log, Search Engine Land, PPC community forums, Google Marketing Live announcements

---

### Audience & Behavioral Intelligence

**Why it matters:** Understanding who converts (not just what keywords they used) unlocks audience-level optimization. Demographic, behavioral, and intent signals from outside Google Ads improve targeting and creative strategy.

**What to track:**
- Customer persona data (age, income, interests of best customers)
- Site behavior patterns (pages visited before converting, session depth)
- Cart abandonment patterns and triggers
- Customer feedback and review language (mines ad copy ideas)
- Social media engagement patterns (what content resonates)
- Email/SMS engagement (opens, clicks — indicates brand affinity)
- Support ticket themes (surface objections and pain points)

**Sources:** GA4 audience reports, Hotjar / FullStory session recordings, Klaviyo / Mailchimp engagement data, review platforms, social listening tools, CX/support platforms

---

## Part 3: Mapping to BrightMatter Ingestion Priorities

### Tier 1 — Ingest Daily (All 500 Accounts)
Campaign-level: spend, conversions, conv_value, CPA, ROAS, impression_share, budget_lost_IS, rank_lost_IS, campaign_type, bidding_strategy, bidding_target, budget, network_settings, status

### Tier 2 — Ingest Weekly (All 500 Accounts)
Keyword-level: Quality Score distribution, match type breakdown, negative keyword count, top/bottom performing keywords. Ad-level: ad strength, RSA asset performance labels. Structural: ad group count, keyword count, extension coverage.

### Tier 3 — Ingest on Change (Event-Driven)
Change history API: every setting change, bid adjustment, budget change, pause/enable, keyword addition/removal — with before/after state and the user who made it.

### Tier 4 — Ingest Daily (External)
Landing page Core Web Vitals and conversion rates (GA4 + PageSpeed). CRM lead quality data. Product availability and pricing (ecommerce accounts).

### Tier 5 — Ingest Weekly (External)
SEO ranking changes for paid keyword overlap. Competitor Auction Insights trends. Google Trends search volume for core terms. Cross-channel attribution data.

### Tier 6 — Ingest as Available (Context Layer)
Seasonal calendars, platform change announcements, industry benchmark updates, client-specific strategy docs, promotional calendars.

---

## Sources Referenced

- Google Ads API Developer Documentation (developers.google.com/google-ads/api)
- Google Ads Help Center — Quality Score (support.google.com/google-ads/answer/6167118)
- Google Ads Help Center — Bidding Strategies (support.google.com/google-ads/faq/10286469)
- Google Ads API — Campaign Types (developers.google.com/google-ads/api/docs/campaigns/overview)
- Google Ads API — Targeting Settings (developers.google.com/google-ads/api/docs/targeting/targeting-settings)
- Google Ads API — Performance Max Reporting (developers.google.com/google-ads/api/performance-max/reporting)
- Google Ads API — AI Max Reporting (developers.google.com/google-ads/api/docs/campaigns/ai-max-for-search-campaigns/ai-max-reporting)
- ALM Corp — Google Search Ads Audit 2026 (almcorp.com/blog/google-search-ads-audit-2026)
- ALM Corp — Performance Max Optimization Controls (almcorp.com/blog/google-ads-performance-max-optimization-controls)
- Affect Group — Google Ads Metrics Explained (affectgroup.com/blog/google-ads-metrics-in-the-interface-and-api-definitions-formulas-and-limits)
- PPC.io — AI Tools for Google Ads (ppc.io/blog/ai-tools-google-ads)
- Segwise — AI Ad Platforms Compared (segwise.ai/blog/ai-ad-platforms-compared-8-tools-machine-learning)
- Roadway AI — How to Make a Google Ads AI Agent (roadwayai.com/blog/how-to-make-a-google-ads-ai-agent)
- Single Grain — Performance Max Framework (singlegrain.com/advertising/master-google-ads-performance-max-with-our-4-step-framework)
- TwoSquares — Quality Score Guide (twosquares.co.uk/blog/google-ads-quality-score-guide)
- Digital Applied — Google Ads Ranking (digitalapplied.com/blog/google-ads-ranking-explained)
- Landingi — Quality Score (landingi.com/digital-advertising/google-ads-quality-score)
