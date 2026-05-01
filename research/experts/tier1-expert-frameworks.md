# Tier 1 Expert Frameworks — Google Ads Pattern Recognition

> Research compiled for **BrightMatter** — a Google Ads pattern recognition engine analyzing 500 accounts to detect patterns, anomalies, and optimization opportunities.
>
> Each expert section extracts their *system*, not opinions — the structured frameworks, quantified thresholds, and data requirements that feed engineering decisions.

---

## Brad Geddes

**Role:** Co-founder of Adalysis (ad testing platform), Author of *Advanced Google AdWords*
**Focus:** Quality Score mechanics, ad testing methodology, account structure theory

### Core Framework

Geddes operates three interlocking systems:

**1. Quality Score Decomposition Model**
Adalysis reverse-engineered the visible Quality Score formula:

```
Visible QS = 1 + Landing Page Experience points + Ad Relevance points + Expected CTR points
```

Each component is rated Above Average / Average / Below Average and contributes weighted points:
- **Expected CTR:** 3.5 points (39% weight) — the dominant factor because high CTR = revenue for Google + relevance signal
- **Ad Relevance:** 2 points (22% weight)
- **Landing Page Experience:** 3.5 points (39% weight)

The visible QS (1–10 scale) is *not* the score used in ad auctions — Google uses a different, hidden range for Ad Rank and CPC calculations.

**2. Alpha-Beta Account Structure**
A campaign architecture that separates keyword discovery from proven performance:
- **Alpha campaigns:** Proven, high-volume keywords in exact match, each in its own Single Keyword Ad Group (SKAG). Maximum control over ad copy, landing page, and bids.
- **Beta campaigns:** Non-exact match keywords (broad match modified / phrase) used to discover new profitable queries. Once a query proves profitable (≥2 conversions within efficiency target), it's promoted to Alpha and excluded from Beta.

**3. Scientific Ad Testing Methodology (7-step system)**
1. Determine hypothesis
2. Decide scale & testing type (single ad group vs. multi-ad group)
3. Choose winner-selection metric
4. Set up tests with "Rotate Indefinitely" ad rotation
5. Wait for statistical significance
6. Pause losers, concentrate impressions on winners
7. Launch next test

Multi-ad group testing examines data across all ad groups at the hypothesis level (template, label, or pattern), revealing which concept performs best account-wide.

### Key Patterns They Identify

| Pattern | Threshold | Implication |
|---------|-----------|-------------|
| QS ≥ 7 | Baseline "good" | Below 7 = priority optimization target |
| QS = 1 | CPC inflated ~400% vs. average | Immediate intervention needed |
| QS = 10 | CPC reduced ~50% vs. average | Protect these keywords |
| Ad test minimum clicks | ≥300 per ad (minimum), 500 (better), 1,000 (ideal) | Below these thresholds, statistical significance is unreliable |
| Ad test minimum conversions | ≥7 per ad (minimum), 15+ (ideal) | Don't declare winners without this volume |
| Ad test minimum duration | ≥1 week (minimum), 1 month (better), 3 buying cycles (ideal) | Prevents day-of-week bias |
| Alpha promotion trigger | ≥2 conversions within efficiency target | Prevents false positives / one-hit wonders |
| Ad group keyword count | < 20 active keywords per ad group | Above 20 = diluted relevance |
| Two-word rule | Every keyword in an ad group shares two root words | Enforces tight thematic grouping |
| Ad Strength vs. conversion rate | Lower Ad Strength can correlate with higher conversion rates | Don't optimize for Ad Strength alone |

**Peel & Stick strategy:** Continuously pull low-CTR / low-QS keywords from ad groups into new ad groups with better-matched ads and landing pages.

### Data Points Needed for Detection

- `keyword.qualityScore` (1–10 visible score)
- `keyword.qualityScoreComponents` (expectedCtr, adRelevance, landingPageExperience — each as ABOVE_AVERAGE, AVERAGE, BELOW_AVERAGE)
- `keyword.impressions` (impression-weighted QS at ad group and campaign level)
- `keyword.matchType` (detect Alpha vs. Beta structure)
- `adGroup.keywordCount` (detect over-stuffed ad groups)
- `ad.clicks`, `ad.conversions`, `ad.impressionShare` (ad testing statistical significance)
- `ad.rotationSetting` (verify "Rotate Indefinitely" is set)
- `campaign.name`, `adGroup.name` (naming convention analysis)
- `searchTerm.query` vs. `keyword.text` (query-to-keyword mapping for Alpha promotion)
- Historical QS trends (weekly snapshots for directional analysis)

### Cross-Account Insights

- **Brand vs. Non-brand:** Always separate into distinct campaigns. Brand keywords will have inflated QS and CTR that masks non-brand performance.
- **High-volume vs. long-tail:** Alpha-Beta structure is most useful for high/medium volume keywords. Long-tail keywords may remain in Beta campaigns indefinitely due to insufficient data — and that's acceptable.
- **Account maturity:** Newer accounts have fewer proven Alphas; the system creates a natural progression from broad discovery to precise targeting as data accumulates.
- **SKAGs in the Smart Bidding era:** Google's looser match types and algorithm improvements mean SKAGs should be consolidated for data density. A properly done consolidation yields ~10% efficiency lift while maintaining control via enhanced conversions, offline conversion tracking, and negative keywords.

### Commonly Misdiagnosed / Overlooked

1. **Quality Score myths that persist:** Long campaign/ad group names don't help QS. Keyword-stuffing landing pages is counterproductive. Adding AdSense doesn't improve QS. Popups to reduce bounce rates can get you banned.
2. **Visible QS ≠ auction QS:** The 1–10 score is a lagging, rounded proxy. Google uses a continuous score with different weightings in real-time auctions. Chasing visible QS improvements may not translate to actual CPC reduction.
3. **Ad Strength is misleading:** Google's "Ad Strength" indicator (for RSAs) does *not* correlate positively with conversion rate — in many cases, lower Ad Strength ads convert better. Don't optimize for Google's Ad Strength metric.
4. **Statistical significance with small data:** Tools may report significance at 13 clicks — this is insufficient. Geddes warns against trusting any result below his minimum thresholds.
5. **Match type contamination:** Without proper negatives, different campaigns/ad groups cannibalize each other by matching the same queries. This is the single most common structural flaw in accounts.

### Top Sources

- https://adalysis.com/quality-score/ — QS formula reverse-engineered
- https://adalysis.com/scientific-ad-testing/ — 7-step ad testing methodology
- https://bgtheory.com/blog/the-complete-adwords-audit-part-6-quality-score/ — QS audit framework
- https://bgtheory.com/blog/the-complete-adwords-audit-part-7-account-structure/ — Account structure audit
- https://bgtheory.com/blog/how-to-capture-control-your-ppc-keywords-to-achieve-a-better-account-structure/ — Alpha-Beta structure
- https://bgtheory.com/blog/how-much-data-do-you-need-to-reach-statistical-significance/ — Statistical significance thresholds
- https://bgtheory.com/blog/dont-fall-for-this-bad-advice-the-worst-quality-score-advice-weve-heard/ — QS myths debunked
- https://searchengineland.com/google-ads-mistakes-avoid-449288 — Top Google Ads mistakes (2026)

---

## Kirk Williams

**Role:** Founder of ZATO Marketing — THE Shopping and PMax specialist
**Focus:** Product feed optimization, Standard Shopping vs. PMax coexistence, feed-level bidding strategies

### Core Framework

Williams operates a **"Segmentation Buffet"** model — there is no single correct PMax structure. Instead, he provides seven structuring methods that can be combined based on account-specific data:

**7 PMax Structuring Methods:**
1. **PMax + Standard Shopping coexistence** — Run both simultaneously; PMax for scale/reach, Standard Shopping for precision/control
2. **Segment by Product Type** — Using custom product type taxonomy (≥3 tiers deep)
3. **Segment by Brand Keywords** — Isolate branded search from non-branded
4. **Segment by Historical Performance** — Group products by proven ROAS buckets
5. **Feed-Only PMax** — PMax without static creative assets, mimicking legacy Smart Shopping (forces Google to use only product feed data)
6. **Segment by New Customer Acquisition** — Target new vs. returning customers differently
7. **Segment by Custom Labels** — Margin tiers, promotions, seasonal flags, bestsellers

**Feed Optimization dual-audience principle:** Product titles must serve two audiences simultaneously — the human (who needs to understand the product at a glance) and the bot (which needs keywords for proper indexing).

### Key Patterns They Identify

| Pattern | Threshold / Rule | Implication |
|---------|-----------------|-------------|
| Title front-loading | First 70 characters (less on mobile) are visible | Critical information must appear before truncation point |
| Title template mismatch | Generic "Brand + Color + Size" templates | One-size-fits-all templates fail for specialized products |
| Product Type depth | ≥3 tiers (e.g., `Cycling > Accessories > Phone Mounts > Road Bike`) | Shallow product types = poor bid granularity |
| GTIN/GPC override cases | Only 4 valid reasons to override Google's auto-categorization: US tax, vertical-specific attributes, restricted goods, taxonomy-based campaigns | Unnecessary overrides waste effort |
| Feed-only PMax trigger | Poor assets or asset-to-product mismatch | Remove creative assets; let feed data drive |
| PMax "Shop Cost" misread | Shop Cost ≠ Shopping SERP only | Includes DPAs across YouTube, Display — not apples-to-apples with Standard Shopping |
| Title testing method | "Poor man's A/B test": control group vs. title-changed group via Attribute Rules or Supplemental Feeds | Measure CTR and impression lift over 2–4 weeks |
| 80/20 feed principle | Focus on high-impact feed optimizations first | Don't optimize every attribute equally |

### Data Points Needed for Detection

- `product.title` (length, keyword presence, front-loading analysis)
- `product.productType` (tier depth count, taxonomy structure)
- `product.gtin` (presence/absence — critical for shared learning signals)
- `product.googleProductCategory` (auto vs. manual override detection)
- `product.customLabels` [0-4] (margin, promotion, seasonal, bestseller flags)
- `campaign.type` (PMax vs. Standard Shopping identification)
- `campaign.assetGroups` (detect feed-only vs. full-asset PMax)
- `pmax.channelBreakdown` (Shop Cost vs. Display vs. Video vs. Search decomposition)
- `product.impressions`, `product.clicks`, `product.conversions` (per-product performance)
- `searchTerms.query` (query-to-product matching for title optimization)
- `product.brand` (brand vs. non-brand segmentation)
- Supplemental feed data (for A/B test detection)

### Cross-Account Insights

- **Ecommerce spend scaling:** Williams advocates the 80/20 principle — start with the highest-impact feed optimizations and only layer complexity when the baseline is profitable.
- **Product category differences:** Title optimization templates must be category-specific. What works for commodity apparel (Brand + Color + Size) fails for specialized equipment (e.g., high-end road bikes need different attributes front-loaded).
- **PMax + Standard Shopping coexistence:** Best suited for large catalogs where PMax ignores long-tail products, branded terms need CPC protection, and low-margin items need margin defense. The hybrid "muscle and scalpel" approach is validated across €500M+ in annual ad spend for 350+ global retailers (per smec data).
- **Brand positioning risk:** PMax prevents advertisers from controlling where their brand appears (YouTube, Display, Gmail placements). For brand-sensitive advertisers, this is a non-trivial risk that raw ROAS numbers don't capture.

### Commonly Misdiagnosed / Overlooked

1. **PMax "Shop Cost" conflation:** Most advertisers believe Shop Cost = Shopping ads on the SERP. It actually includes Dynamic Product Ads across YouTube, Display, and other surfaces. PMax and Standard Shopping can "never be apples to apples" in comparison.
2. **Transparency deficit:** You cannot see which YouTube videos, Display placements, or keywords trigger your PMax ads. This prevents strategic brand positioning decisions and removes fiduciary oversight of client budgets.
3. **Product Type vs. Google Product Category confusion:** Product Type is "for your bids" (fully customizable, mirrors your site structure). Google Product Category is "for the bots" (Google's taxonomy). Most advertisers conflate these and optimize the wrong one.
4. **Over-reliance on automation without feed quality:** PMax's algorithm is only as good as the feed data. Poor feed data = poor automation decisions, regardless of bid strategy sophistication.
5. **Ignoring increased ROAS from remarketing expansion:** When PMax shows "better" ROAS than Standard Shopping, it may be expanding remarketing audiences — not actually finding new customers more efficiently.

### Top Sources

- https://zatomarketing.com/blog/how-to-structure-performance-max-campaigns-7-ways — 7 PMax structuring methods
- https://zatomarketing.com/blog/setting-up-feed-only-pmax-campaign-step-by-step-walkthrough — Feed-Only PMax walkthrough
- https://zatomarketing.com/blog/how-to-optimize-google-shopping-product-titles---google-merchant-center-mastery — Title optimization
- https://zatomarketing.com/blog/how-to-optimize-shopping-ads-google-product-category-google-merchant-center-mastery — Product Category vs. Product Type
- https://zatomarketing.com/blog/heres-why-the-new-pmax-channel-reporting-rocks — PMax Channel Report analysis
- https://zatomarketing.com/blog/the-problem-of-platform-transparency — Transparency problem essay
- https://www.lunio.ai/podcasts/pmax-for-ecommerce — Podcast on PMax optimization for ecommerce

---

## Frederick Vallaeys

**Role:** CEO of Optmyzr, former Google employee #500 (AdWords Evangelist)
**Focus:** Automation-era PPC strategy, rule-based optimization layered on Smart Bidding, Google AI failure patterns
**Author:** *Unlevel the Playing Field*, *Digital Marketing in an AI World*

### Core Framework

Vallaeys' central thesis is **Automation Layering** — stacking human-controlled rule-based automations on top of Google's platform automation to create security, control, and visibility. BCG research he cites shows this approach delivers **15% better campaign performance** than automation alone.

**Three-pillar framework:**
1. **Bidding layer:** Don't fight Smart Bidding — shape it. Use Value Rules (conversion value multipliers) instead of traditional bid adjustments. Feed better business data through Offline Conversion Import (OCI), Conversion Value Adjustments, and Enhanced Conversions.
2. **Targeting layer:** Monitor what Google's automation is matching and build negative keyword scripts to correct errors automatically. Use audience signals and Value Rules to steer targeting without overriding it.
3. **Messaging layer:** Human creativity remains the differentiator. Test ad copy, landing pages, and creative assets — areas where algorithms can't replicate strategic intent.

**Rule Engine architecture (Optmyzr's If-This-Then-That system):**
- Conditions → Actions → Notifications (email, Slack, Teams)
- Supports multiple date range comparisons (e.g., last 30 days vs. previous 30 days)
- Dynamic thresholds using relative comparisons (e.g., "1.5× ad group CPA") that scale across accounts
- External data integration via Google Sheets (holiday calendars, weather data, inventory feeds)
- Cooldown windows to prevent excessive automated edits

### Key Patterns They Identify

| Pattern | Threshold / Rule | Implication |
|---------|-----------------|-------------|
| Smart Bidding learning period | 7–14 days; requires 30 conversions/30d (tCPA) or 50 conversions/30d (tROAS) | Don't make changes during learning; campaigns need to exit learning before evaluation |
| Budget pacing anomaly | Mid-month spend ≠ 50–60% of monthly budget | Underpacing or overpacing indicates misallocation or automation error |
| CPC spike detection | Average CPC exceeds historical threshold | Smart Bidding algorithmic malfunction (has happened multiple times at scale) |
| Keyword zero-conversion rule | No conversions in 60 days AND spend > 3× CPA goal | Pause immediately — automation won't catch this fast enough |
| Conversion tracking breakage | 47% of "stuck" Smart Bidding campaigns | Broken tracking inflates CPA by 40–80%; the algorithm optimizes confidently toward wrong data |
| Secondary conversion pollution | Non-primary conversions (phone clicks, page views) in Conversions column | Corrupts bid signal; must use "primary" vs. "secondary" classification |
| Conversion window mismatch | Tracking window ≠ actual sales cycle (e.g., 30-day window on 90-day cycle) | Systematic underbidding due to undercounted conversions |
| Value Rules trap | Replicating bid adjustments with Value Rules | "Doubles up" on what automation already does — must use for *new* business signals only |
| Change velocity alert | Multiple edits to same campaign within short timeframe | Indicates human or automation thrashing; trigger cooldown |

### Data Points Needed for Detection

- `campaign.biddingStrategy` (Smart Bidding type identification)
- `campaign.biddingStrategyStatus` (learning, limited, eligible)
- `campaign.cost`, `campaign.budget` (budget pacing calculations)
- `keyword.cost`, `keyword.conversions`, `keyword.cpa` (zero-conversion keyword detection)
- `conversionAction.type`, `conversionAction.category`, `conversionAction.isPrimary` (conversion tracking audit)
- `conversionAction.conversionWindow` (window vs. sales cycle mismatch)
- `campaign.valueRules` (Value Rule configuration audit)
- `changeHistory.changes` (change velocity monitoring)
- `campaign.averageCpc` with historical comparison (CPC spike detection)
- `account.conversionTracking.status` (tracking health check)
- Budget spend vs. time elapsed in billing period (pacing ratio)

### Cross-Account Insights

- **Google's automation is designed for less-experienced advertisers:** It opens new markets for Google's revenue but poorly serves expert practitioners. Automation layering is specifically the expert's counter-strategy.
- **Agency scale advantage:** Rules created once can be applied globally across hundreds of accounts via Optmyzr's "Global Strategies" feature. This makes cross-account pattern detection a built-in capability.
- **Economic volatility:** External events (supply chain disruptions, seasonal shifts, policy changes) invalidate historical data that Smart Bidding relies on. Automation layering acts as insurance — limiting damage until the system recalibrates.
- **Vertical differences:** E-commerce accounts benefit most from Value Rules and ROAS targets. Lead gen accounts need OCI and conversion value adjustments because the true value is realized downstream. Weather-sensitive verticals (HVAC, seasonal retail) benefit from external data integration.

### Commonly Misdiagnosed / Overlooked

1. **"Set it and forget it" with Smart Bidding:** Google promotes this mindset, but it exposes campaigns to algorithmic malfunctions, CPC spikes, and budget blowouts that can persist for hours or days before detection.
2. **Conversion tracking is assumed correct:** 47% of underperforming Smart Bidding campaigns trace to broken or misconfigured conversion tracking — not strategy problems. This is the #1 diagnostic to check first.
3. **Secondary conversions corrupting signals:** Including phone clicks, page views, or other micro-conversions in the "Conversions" column sends conflicting signals to Smart Bidding. Most accounts have this misconfigured.
4. **Google Ads reps push revenue-maximizing changes:** Since 2021, Google reps actively push automated recommendations that serve Google's revenue goals, not advertiser goals. Auto-applied recommendations should be reviewed and often rejected.
5. **Value Rules misuse:** Advertisers replicate existing bid adjustments (device, location, audience) through Value Rules, effectively "doubling up" on signals Google is already factoring. Value Rules should only encode *new* business signals the algorithm can't see.

### Top Sources

- https://www.optmyzr.com/books/unlevel — *Unlevel the Playing Field* book
- https://www.optmyzr.com/blog/automation-layering-ppc/ — Automation layering comprehensive guide
- https://www.optmyzr.com/blog/advanced-rule-engine-strategies/ — 8 Rule Engine strategies from customer accounts
- https://www.optmyzr.com/blog/improve-google-ads-smart-bidding-performance/ — 3 ways to improve Smart Bidding
- https://www.optmyzr.com/blog/bid-adjustments-back-smart-bidding-google/ — Value Rules as bid adjustment alternative
- https://www.optmyzr.com/blog/value-based-bidding-guide/ — Value-Based Bidding guide
- https://www.optmyzr.com/solutions/rule-engine/ — Rule Engine product documentation
- https://searchengineland.com/automation-layering-is-driving-ppc-so-get-onboard-in-2020-327123 — Automation layering origin essay
- https://www.searchenginejournal.com/google-ads-automation-layering-with-frederick-vallaeys-podcast/328795/ — Podcast on automation layering

---

## Miles McNair / Smarter Ecommerce (smec)

**Role:** smec is an ecommerce PPC technology company managing €650M+ in ad spend across 360+ leading ecommerce brands. Mike Ryan (Head of Ecommerce Insights) leads much of the published research.
**Focus:** PMax Campaign Orchestration, Dynamic Segments, multi-dimensional product scoring, data density thresholds

### Core Framework

**Campaign Orchestration** — a four-tier maturity model for PMax optimization, from basic to advanced:

**Tier 1 (Worst): Single Campaign Black Box**
- One full-funnel campaign, single tROAS target
- Google optimizes auction-by-auction with no business context
- A handful of "hero" products dominate spend; if one goes out of stock, performance nosedives
- Only appropriate for new PMax adopters or very small catalogs

**Tier 2 (Bad): 1-Dimensional Segmentation**
- Products grouped by a single attribute (e.g., margin tier) or a single performance snapshot (volume × efficiency quadrant)
- Fails because: ~50% of clicked products are either not purchased or purchased alongside other products — the margin of clicked products ≠ basket margin
- Performance quadrant approach results in 80–90% of products in one "low data" bucket, creating self-fulfilling prophecies (sleepers stay sleepers)

**Tier 3 (OK): Business Data Scoring**
- Multi-attribute scoring using Custom Labels fed via Google Sheets scripts
- Incorporates gross margin, stock availability, seasonal demand
- Limitation: Refreshing data for thousands of products daily is error-prone and doesn't scale; constrained by 5 Custom Label slots

**Tier 4 (Best): Campaign Orchestration**
- Real-time, multi-dimensional system with four technical steps:
  1. **Unified Data Layer** — Merge ERP data (stock depth, return rates, contribution margins), competitor intelligence (price gaps vs. Amazon), and Google Ads data (historical CVR, impression share lost) into a Master Feed
  2. **Multi-Dimensional Scoring** — Weighted index for every Item ID: `Score = (Gross Margin % × W1) + (Stock Velocity × W2) + (Price Competitiveness × W3)` → dynamic score 1–100 per product
  3. **Dynamic Custom Label Injection** — Score ranges mapped to labels via API (e.g., 80–100 = "Margin Drivers", 50–79 = "High Potential", 0–49 = "Low Potential")
  4. **Campaign Matrix with Automated Re-assignment** — Products automatically move between campaigns as scores change (stock drops, price improves, performance shifts)

### Key Patterns They Identify

| Pattern | Threshold | Implication |
|---------|-----------|-------------|
| PMax conversion volume vs. ROAS achievement | < 30 conv/month: unreliable | Campaigns below this are gambling |
| | 60–90 conv/month: ~50/50 hit rate | Still not safe for tROAS targets |
| | **150+ conv/month: sweet spot** | PMax consistently hits/exceeds tROAS |
| Data dilution from over-segmentation | More campaigns = fewer conversions per campaign | Spreading data across too many campaigns reduces tROAS achievement |
| Margin-based segmentation failure | ~50% of clicked products not purchased or cross-purchased | Clicked product margin ≠ basket margin; margin-based campaigns optimize toward wrong signal |
| Hero product dependency | Small % of products drive majority of spend | If heroes go out of stock, entire campaign performance collapses |
| SmartScoreAI "Neighborhood Effect" | Products with no conversion history scored via comparable peers | 100% of catalog receives a performance prediction |
| ROAS threshold re-assignment | Product ROAS drops below target (e.g., 3.0) | Auto-reassign to lower-priority campaign segment |
| Daily tROAS adjustment | Based on product performance shifts and market seasonality | Static tROAS targets lag market reality |

**SmartScoreAI methodology:** Predictive scoring that synthesizes historical performance, price competitiveness, and first-party data into a single metric. Uses the "Neighborhood Effect" — analyzing comparable peer products to predict performance for items without individual click history. This ensures long-tail products aren't permanently ignored.

### Data Points Needed for Detection

- `product.itemId` (per-SKU tracking)
- `product.conversions`, `product.cost`, `product.revenue` (ROAS and performance bucketing)
- `product.impressions`, `product.clicks` (impression share and engagement analysis)
- `campaign.conversions` (campaign-level data density check — 150+/month threshold)
- `product.customLabels` [0-4] (current segmentation labels)
- External: `erp.stockDepth`, `erp.returnRate`, `erp.contributionMargin` (ERP integration)
- External: `competitor.price`, `competitor.priceGap` (price competitiveness)
- `campaign.targetRoas` (tROAS target vs. actual achievement)
- `product.availability` (real-time inventory sync)
- `campaign.impressionShareLostBudget` (budget constraint detection)
- Historical conversion data by product (for SmartScoreAI training)

### Cross-Account Insights

- **Scale matters enormously:** Research from 14,000 PMax data points shows the relationship between conversion volume and ROAS achievement is consistent across retailers. The 150 conv/month threshold is universal, not vertical-specific.
- **Standard Shopping shows same pattern:** The data density–performance correlation holds for Standard Shopping campaigns too — it's a Smart Bidding phenomenon, not a PMax-specific one.
- **Large catalog retailers benefit most from orchestration:** Retailers with 10K+ SKUs see the biggest gains because static segmentation cannot adequately classify that many products.
- **Vertical differences in orchestration weights:** Fashion retailers weight stock velocity and seasonality higher. Electronics retailers weight price competitiveness higher. Grocery/FMCG weights availability and sell-through rate highest.
- **Managed spend context:** smec's insights are derived from €650M+ in annual ad spend across 360+ brands including Decathlon (+52% ROAS uplift), Lookfantastic, Intersport, and MyProtein.

### Commonly Misdiagnosed / Overlooked

1. **More campaigns = more control is a myth:** The opposite is often true. Over-segmentation dilutes data density and hands more uncontrolled decisions to PMax. Fewer, smarter campaigns with dynamic product routing outperform granular campaign matrices.
2. **Margin-based segmentation is fundamentally flawed:** Because ~50% of clicked products aren't purchased (or are cross-purchased), clustering by product margin ≠ optimizing for basket profitability. This is the most common "seems logical but fails" structure.
3. **Performance quadrant trap:** The classic "high volume / high efficiency" 2×2 matrix results in 80–90% of products in a "low data" bucket with no path out. Products identified as sleepers remain sleepers because they never receive enough exposure.
4. **Static labels are obsolete the moment they're uploaded:** Inventory levels fluctuate hourly, competitors adjust pricing, demand shifts seasonally. Any segmentation that requires manual refresh is fighting entropy.
5. **Conversion count thresholds are widely underestimated:** Google says 15 conversions is enough for Smart Bidding. smec's data shows performance is genuinely unreliable below 150/month. Most advertisers operate in the "gambling zone."

### Top Sources

- https://smarter-ecommerce.com/blog/en/ecommerce/the-ultimate-ecommerce-campaign-optimization-playbook-for-pmax/ — 4-tier PMax optimization framework
- https://smarter-ecommerce.com/blog/en/google-ads/how-much-data-does-pmax-need-a-data-driven-guide-to-target-roas/ — 14,000 data point conversion volume analysis
- https://smarter-ecommerce.com/blog/en/platform/what-are-dynamic-segments/ — Dynamic Segments methodology
- https://smarter-ecommerce.com/blog/en/platform/what-is-smartscoreai-for-product-segmentation-and-how-does-it-work/ — SmartScoreAI predictive scoring
- https://smarter-ecommerce.com/blog/en/platform/which-tasks-does-the-smec-campaign-orchestrator-automate/ — Campaign Orchestrator automation details
- https://smarter-ecommerce.com/blog/en/google-shopping/how-to-run-google-shopping-alongside-performance-max-in-2026/ — PMax + Standard Shopping coexistence (2026)
- https://smarter-ecommerce.com/blog/en/google-ads/state-of-performance-max-campaigns-2025/ — State of PMax analysis

---

## Mike Rhodes

**Role:** Founder of WebSavvy (sold 2023 after 17 years, one of Google's top 18 agencies globally, $100M+ managed spend) and AgencySavvy
**Focus:** Agency-scale management, Google Ads Scripts for automated monitoring, PMax transparency tools

### Core Framework

Rhodes operates a **Scripts + Audit + Checklist** system designed for agencies managing dozens to hundreds of accounts:

**1. PMax Insights Script (3,200+ lines of code)**
Automatically extracts PMax "black box" data into organized Google Sheets with these monitoring tabs:
- **Channel Spend Breakdown:** Shopping vs. Video vs. Display vs. Search/Other allocation
- **Asset Group Performance:** Spend, clicks, conversions, ROAS, AOV per asset group
- **Product Performance Buckets:** Every product auto-classified into 6 categories
- **Search Category Analysis:** Brand vs. non-brand traffic decomposition
- **Placement Tracking:** Which websites, YouTube channels, and apps ads appear on
- **Change History:** All modifications alongside performance data (who changed what, when)

**2. Product Performance Bucketing System (6 categories):**

| Bucket | Definition | Action |
|--------|-----------|--------|
| **Zombies** | Products receiving impressions but virtually zero engagement | Investigate feed quality or exclude |
| **Zero Conv** | Products getting clicks but no conversions | Evaluate landing page, pricing, or exclude |
| **Meh** | Underperforming products — marginal results | Monitor or restructure |
| **Flukes** | Inconsistent performers — spike then disappear | Don't over-invest based on temporary signal |
| **Costly** | High cost, low ROAS — actively losing money | Fix immediately or exclude |
| **Profitable** | Strong ROAS, consistent performance | Protect and scale spend |

**3. Agency-Scale Quick Wins Audit (8020Agent):**
Automated checks across all client accounts:
- Search partners enabled (often wasted spend)
- Display in Search campaigns (targeting contamination)
- Performance drops vs. prior period
- Location targeting settings misconfigured
- Empty ad groups
- Disapproved ads

**4. 137-Question Audit Framework:**
Three-step audit methodology applied quarterly by someone *other than* the account manager:
1. High-level account overview
2. Data segmentation analysis
3. Granular diagnostic review

Each finding documented with: Insight → Recommended Action → Expected Business Impact.

### Key Patterns They Identify

| Pattern | Signal | Action |
|---------|--------|--------|
| Zombie products | High impressions, near-zero clicks | Feed quality issue or irrelevant targeting |
| Costly products | Spend > threshold, ROAS < target | Immediate exclusion or landing page fix |
| Channel spend shift | PMax reallocating budget from Shopping to Display/Video | May indicate poor asset quality or audience exhaustion |
| Brand vs. non-brand ratio | Non-brand search terms declining as % of total | PMax may be cannibalizing brand traffic |
| Search partners waste | Enabled by default, often 30–50% worse performance | Disable unless proven otherwise |
| Display in Search | Targeting contamination | Separate immediately |
| Change history anomalies | Unexplained changes correlating with performance drops | Cross-reference who/what/when |
| Product performance instability (Flukes) | Products spike then disappear | Don't over-allocate budget to these |

### Data Points Needed for Detection

- `pmax.channelBreakdown` (Shopping / Video / Display / Search spend allocation)
- `product.impressions`, `product.clicks`, `product.conversions`, `product.cost` (6-bucket classification)
- `product.roas` or derived `product.revenue / product.cost` (profitability bucketing)
- `campaign.searchPartners` (enabled/disabled check)
- `campaign.networkSettings` (Display in Search detection)
- `searchTerms.category` (brand vs. non-brand classification)
- `placements.url`, `placements.youtubeChannel`, `placements.mobileApp` (placement quality audit)
- `changeHistory.user`, `changeHistory.timestamp`, `changeHistory.changeType` (change tracking)
- `ad.approvalStatus` (disapproved ad detection)
- `adGroup.adCount` (empty ad group detection)
- `campaign.locationTargeting` (settings audit)
- AOV from Shopping ads (average order value per product/category)

### Cross-Account Insights

- **Operational discipline > strategy:** Most accounts don't fail from one bad decision but from unclear processes, inconsistent optimizations, and poor documentation. The weekly management checklist is more valuable than any single optimization.
- **Scale-tested architecture:** The PMax Insights Script has been tested on portfolios with 6,000,000+ products across agencies like Dentsu, Merkle, and Publicis. The monitoring patterns are proven at enterprise scale.
- **MCC load balancing:** For agencies using the multi-account script version, Rhodes recommends processing 10–15 accounts per hour to avoid API rate limiting.
- **Audit cross-pollination:** Quarterly audits conducted by someone *other* than the account manager catch blind spots — the person running the account develops normalized assumptions about what's "normal."
- **Privacy-first architecture:** All data stored in Google Sheets, not external servers. This matters for client trust and data governance at agency scale.

### Commonly Misdiagnosed / Overlooked

1. **PMax "good ROAS" masking channel waste:** PMax can report strong overall ROAS while quietly shifting budget to Display or Video channels that produce low-quality conversions. Without channel-level visibility, agencies can't see this.
2. **Search partners enabled by default:** This Google default often wastes 30–50% of the spend it receives but is rarely checked because it's not prominently displayed.
3. **Flukes treated as winners:** Products that spike temporarily get additional budget, then performance disappears. Without historical categorization, agencies repeatedly over-invest in unstable performers.
4. **Change history attribution gaps:** When multiple people (account managers, Google reps, auto-applied recommendations) make changes, performance drops can't be attributed without systematic change tracking.
5. **"Zombie" products ignored because they don't cost much individually:** At scale (6M+ products), zombie products collectively waste significant budget through tiny individual bleeds that don't trigger individual alerts.

### Top Sources

- https://mikerhodes.com.au/scripts/pmax — PMax Insights Script product page
- https://mikerhodes.com.au/scripts/help/pmax-insights — PMax script documentation
- https://mikerhodes.com.au/scripts/mcc — MCC multi-account script
- https://mikerhodes.com.au/scripts/help/getting-started — Configuration and setup guide
- https://mikerhodes.com.au/agent — 8020Agent (Quick Wins audit tool)
- https://github.com/agencysavvy/pmax/ — Open-source PMax script (GitHub)
- https://pmaxscript.com/ — PMax script landing page (8,400+ users)

---

## Andrew Lolk

**Role:** Founder of SavvyRevenue — ecommerce-specialized Google Ads agency (10+ years)
**Focus:** Ecommerce Google Ads, Shopping campaign architecture, PMax for ecommerce, feed optimization

### Core Framework

Lolk operates a **data-driven minimalism** philosophy: don't add complexity unless the data justifies it. His system has three interlocking components:

**1. Two-Stage Feed Optimization Framework:**

**Stage 1 — Feed Hygiene (pass/fail foundation):**
- Goal: 100% accuracy on factual attributes. Binary: correct or not correct.
- Checklist approach: List all attributes, mark each as Exists & Correct / Needs Fix / Not Applicable.
- Non-negotiable attributes: GTIN, availability, brand, color, condition, material.
- GTIN is the single most important attribute — it links your product to competitors' products, enabling shared product ratings (500 competitor reviews appear on your ad) and shared search query learning.
- Done once, rarely revisited.

**Stage 2 — True Feed Optimization (high-leverage strategic work):**
- **Visibility optimization:** Product title (front-load critical info, match search intent, don't over-template), product ratings (need 50+ total reviews to enter program), images (only fix if systematically bad).
- **Analysis/structure optimization:** Custom Labels for internal segmentation:
  - Bestseller / Saboteur classification
  - On Sale vs. Regular Price
  - Price Range / AOV buckets
  - Margin tiers (for profit-based bidding)
- **Explicit don'ts:** Don't manually optimize product descriptions (website description is good enough). Don't manually override Google Product Category (Google auto-categorizes well).

**2. Pre-Flight Segmentation Rules:**

Two non-negotiable prerequisites before creating any campaign split:
- **Rule #1: Always split Brand vs. Non-Brand.** This is the foundational structural split. Brand intent and performance are so fundamentally different they must be isolated.
- **Rule #2: Minimum 100 conversions per campaign per month.** Google says 15 is enough — Lolk calls this insufficient. Below 100, Smart Bidding lacks the data density to optimize effectively.

**3. Analyst's Framework for Justifying Segmentation:**

Before building a new campaign structure, answer: *What are you trying to solve?*
- There must be a **significant performance difference** between proposed segments, OR
- You need **significantly different ROAS/tCPA targets** (minimum 20% difference — a 600% vs. 650% split is pointless)
- Focus on **conversion rate** as the key diagnostic metric, not ROAS (which will naturally cluster around target due to Smart Bidding's optimization)
- If no historical data for proposed segmentation: create the custom label, wait 2–12 weeks, *then* analyze

### Key Patterns They Identify

**7 Shopping Campaign Structures That Work:**

| Structure | Use Case | Key Metric |
|-----------|----------|------------|
| Bestseller vs. Unprofitable | Large catalogs with clear performance gaps | Conversion rate gap |
| Hero vs. Accessories | High-AOV core products vs. low-AOV add-ons | AOV and ROAS difference |
| Sale vs. Normal Price | Products on sale have fundamentally different CVR | Conversion rate uplift during sale |
| Seasonality | Swimwear, winter coats, category-specific timing | Seasonal CVR patterns |
| Price Competitiveness | Products where you have price advantage vs. competitors | CVR by competitive position |
| Price/AOV Split | Different price points need different bidding logic | POAS by AOV bucket |
| Private Label vs. External Brands | When PL is ≥20% of catalog, margin difference justifies separation | Margin % and POAS differential |

**4 Structures That Hurt Performance:**

| Structure | Why It Fails |
|-----------|-------------|
| **Margin-based segmentation** | Users don't always buy what they click — attribution breaks; margin of clicked product ≠ basket margin |
| **Product Variations** (bundles, colors, sizes) | Same keywords, same users — needless complexity with no Smart Bidding benefit |
| **Categories & Brands** (without performance difference) | Segmentation for organization's sake thins out data without improving decisions |
| **Geographic splits** | Not how Google Ads works for ecommerce; use location bid adjustments instead |

| Pattern | Threshold | Implication |
|---------|-----------|-------------|
| Minimum campaign conversions | 100/month (Lolk's rule); Google says 15 | Below 100 = insufficient data for Smart Bidding |
| Minimum segmentation performance difference | ≥20% difference in ROAS targets | Below 20% = pointless split that thins data |
| PMax-to-Standard Shopping switch threshold | ≥30 conversions/month (don't switch with less) | Below 30 = insufficient data for either format |
| GTIN coverage | 100% where applicable | Missing GTINs = invisible to shared learning and ratings |
| Custom label utilization | Most underutilized feed attribute | Bestsellers, saboteurs, sale status, price range, margin |
| Structure validation timeline | 3–12 months | Don't judge new structures prematurely; full business cycles needed |
| Feed hygiene audit | One-time checklist per product catalog | Foundation must be correct before optimization begins |

### Data Points Needed for Detection

- `product.gtin` (presence check — non-negotiable)
- `product.availability`, `product.brand`, `product.color`, `product.condition`, `product.material` (hygiene checklist)
- `product.title` (length, front-loading analysis, keyword-intent alignment)
- `product.customLabels` [0-4] (bestseller/saboteur, sale status, price range, margin, private label flag)
- `campaign.conversions` (per campaign — 100/month minimum check)
- `campaign.conversionRate` (key diagnostic for justifying splits — more informative than ROAS)
- `product.revenue / product.cost` (ROAS at product and campaign level)
- `product.averageOrderValue` (AOV bucketing)
- `product.salePrice` vs. `product.price` (sale detection)
- `product.productRatings` (review count — need 50+ for program eligibility)
- `product.brand` + internal margin data (private label identification)
- Competitor pricing data (price competitiveness segmentation)
- `campaign.brandVsNonBrand` (query classification for mandatory brand split)

### Cross-Account Insights

- **Ecommerce ≠ Lead Gen fundamentally:** Shopping optimization is "most comparable to landing page optimization" — it's about feed quality, product data, and visual presentation. Text ad optimization (keyword → ad copy → landing page) is a different skill set. BrightMatter should treat these as distinct analysis paths.
- **"If you can't win with one campaign, you can't win at all":** For any account, profitability with a single campaign is the baseline test. If the baseline fails, adding campaign complexity makes it worse, not better.
- **Spend scaling trajectory:** Start with one campaign → split brand vs. non-brand → add segmentation only when conversion volume supports it (100+/month per campaign). This is a *maturation path*, not a starting configuration.
- **Private label signal:** If ≥20% of catalog is private label, this is a strong segmentation signal because margin differences justify different bidding strategies.
- **Seasonal businesses need patient validation:** Campaign structures for seasonal products (swimwear, winter gear) need a full year to validate. Premature judgment leads to abandoned structures that might have worked.

### Commonly Misdiagnosed / Overlooked

1. **Over-segmentation is the #1 structural mistake:** Advertisers create 10 campaigns when they need 2. Each split thins out data, weakens Smart Bidding, and creates management overhead. More structure ≠ better performance.
2. **ROAS is a misleading diagnostic for segmentation decisions:** Because Smart Bidding optimizes *toward* your ROAS target, ROAS naturally clusters around that target — masking underlying performance differences. Conversion rate tells the real story.
3. **Margin-based campaign structures seem logical but fail:** The fundamental problem is that clicked product ≠ purchased product ~50% of the time. Optimizing bids by product margin doesn't optimize for basket profitability.
4. **Product descriptions are a time sink:** Lolk hasn't manually optimized a product description in years. The website description is almost always sufficient. Most agencies waste hours here with zero impact.
5. **Bestseller campaigns can secretly hurt performance:** Isolating bestsellers in premium campaigns can actually limit their exposure if the structure starves other campaigns of the data they need. The system should be analyzed holistically.
6. **GTIN omission is invisible but devastating:** Without GTINs, your products can't access shared product ratings or search query learning from competitors selling the same items. Many advertisers skip this because it's tedious, not realizing the compounding competitive disadvantage.

### Top Sources

- https://savvyrevenue.com/blog/google-shopping-feed-optimization-framework/ — Two-Stage Feed Optimization Framework
- https://savvyrevenue.com/blog/shopping-ads-campaign-structure/ — 7 structures that work, 4 that don't
- https://savvyrevenue.com/blog/shopping-campaign-structure/ — Baseline campaign structure ("start with one")
- https://savvyrevenue.com/blog/google-shopping-feed-optimization/ — Prioritized feed optimization list
- https://savvyrevenue.com/blog/advanced-shopping-feed-optimization/ — 7 key areas for advanced feed work
- https://savvyrevenue.com/blog/advanced-google-shopping-campaign-optimization/ — In-depth Shopping optimization
- https://savvyrevenue.com/blog/performance-max/ — PMax analysis for ecommerce
- https://savvyrevenue.com/blog/pmax-to-standard-shopping/ — PMax to Standard Shopping migration guide
- https://savvyrevenue.com/blog/from-p-max-to-standard-shopping/ — Standard Shopping migration methodology

---

## Cross-Expert Synthesis: Patterns for BrightMatter

### Universal Patterns Across All 6 Experts

1. **Data density trumps granularity.** Every expert warns against over-segmentation. Whether it's Geddes' SKAG consolidation, Lolk's 100-conversion rule, smec's 150-conversion threshold, or Vallaeys' automation layering — the consensus is: fewer, smarter segments outperform many granular ones.

2. **Brand vs. non-brand split is non-negotiable.** Geddes, Lolk, Williams, and Rhodes all mandate this as the foundational structural decision.

3. **Conversion tracking is the #1 failure point.** Vallaeys finds 47% of stuck campaigns trace to tracking issues. Rhodes' Quick Wins audit checks for it first. Lolk's baseline test assumes tracking is correct. BrightMatter should make conversion tracking health the first diagnostic check.

4. **Feed quality is the bottleneck for Shopping/PMax.** Williams, Lolk, and smec all emphasize that automation is only as good as the data it receives. GTIN coverage, title optimization, and custom label utilization are leading indicators of performance potential.

5. **Static structures decay immediately.** smec's "obsolete the moment they're uploaded" principle applies to any manual segmentation. Williams advocates dynamic routing. Lolk accepts simpler structures but requires ongoing validation.

### Key Thresholds for BrightMatter Detection Rules

| Metric | Threshold | Source | Priority |
|--------|-----------|--------|----------|
| Quality Score | < 7 = intervention needed | Geddes | High |
| Quality Score | 1 = 400% CPC inflation | Geddes | Critical |
| Campaign conversions/month | < 30 = unreliable | smec | Critical |
| Campaign conversions/month | < 100 = insufficient for Smart Bidding | Lolk | High |
| Campaign conversions/month | 150+ = reliable sweet spot | smec | Monitoring |
| Ad test clicks per ad | < 300 = insufficient | Geddes | High |
| Ad test conversions per ad | < 7 = insufficient | Geddes | High |
| ROAS target difference for split | < 20% = pointless split | Lolk | High |
| Zero-conversion keyword spend | > 3× CPA goal in 60 days | Vallaeys | Critical |
| Smart Bidding learning | 7–14 days; 30 conv (tCPA) / 50 conv (tROAS) | Vallaeys | Monitoring |
| Budget pacing mid-month | ≠ 50–60% of monthly budget | Vallaeys | High |
| GTIN coverage | < 100% = competitive disadvantage | Lolk, Williams | High |
| Product title length | > 70 chars = truncation risk | Williams | Medium |
| Custom label utilization | 0 of 5 used = missed opportunity | Lolk, Williams, smec | Medium |
| Search partners enabled | Default on = likely wasted spend | Rhodes | High |
| Product type depth | < 3 tiers = poor bid granularity | Williams | Medium |

### API Data Requirements Summary

**Google Ads API fields needed across all expert frameworks:**
- Campaign: type, biddingStrategy, status, budget, cost, conversions, conversionRate, targetRoas, targetCpa, networkSettings, searchPartners, locationTargeting
- Keyword: text, matchType, qualityScore, qualityScoreComponents, impressions, clicks, cost, conversions, cpa
- Ad: type, strength, headlines, descriptions, clicks, impressions, conversions, rotationSetting, approvalStatus
- Search Terms: query, impressions, clicks, conversions, cost
- Product (Shopping/PMax): itemId, title, gtin, productType, googleProductCategory, customLabels, brand, availability, condition, price, salePrice, impressions, clicks, conversions, cost, revenue
- PMax: channelBreakdown, assetGroups, placements, searchCategories
- Change History: user, timestamp, changeType, affectedEntity
- Conversion Actions: type, category, isPrimary, conversionWindow, status

**External data integrations needed (for advanced detection):**
- ERP/inventory: stock depth, return rates, contribution margins
- Competitor pricing: price gaps, competitive position
- CRM/offline: offline conversion data, customer lifetime value
- Weather/calendar: seasonal signals, holiday calendars
