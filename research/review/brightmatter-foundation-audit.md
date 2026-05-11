# BrightMatter Foundation Audit: Gaps, Corrections & Missing Detectors

---

## 1. Classification Corrections (Urgent)

The current classifier has a bug — it assigned "pets" as the vertical for 8 of 21 accounts and misidentified several business types. Here are the corrections based on actual conversion actions, campaign types, and account names:

| Account | Current | Correct Business Type | Correct Vertical | Evidence |
|---------|---------|----------------------|-------------------|----------|
| APL New-Clean for 2019 | ecommerce / automotive | ecommerce | footwear / apparel | AthleticPropulsionLabs.com in conversion names, PURCHASE conversions, Shopping campaigns |
| Arcis Golf | ecommerce / outdoor | lead_gen | hospitality / golf | 0 conversion value, 175 search campaigns = golf course memberships/tee times |
| BMS Moving & Storage | ecommerce / pets | local_services | moving | Search-only, $124 CPA, "Moving & Storage" in name |
| Binance.US | ecommerce / pets | lead_gen | fintech / crypto | Crypto exchange, high conv volume + $0 value = signups not purchases |
| Corwin Master CID | ecommerce / food_beverage | unknown (multi-brand) | multi-vertical | "Master CID" = multi-client container, low ROAS 0.3x |
| Coway - US | ecommerce / pets | ecommerce | home_appliances | Coway makes water purifiers/air purifiers, $16.1x ROAS |
| Funko | ecommerce / pets | ecommerce | collectibles / toys | Pop figures, $3.3x ROAS, Shopping + PMax + Demand Gen |
| Hawke Media - Internal | ecommerce / - | lead_gen | marketing_agency | The agency's own lead gen, $580 CPA, Search + Demand Gen |
| Invited, USA | lead_gen / finance | lead_gen | hospitality / golf | ClubCorp/Invited = golf/country club memberships, 175 campaigns, $0 value |
| JECT | ecommerce / automotive | ecommerce | beauty / skincare | JECT makes skincare products, $9.5x ROAS |
| JHT - Strat | ecommerce / pets | lead_gen | unknown | $0 conversion value = lead gen, not ecommerce |
| LOCKLY | ecommerce / pets | ecommerce | smart_home / hardware | Smart locks, $5.1x ROAS — but 26K PMax conversions vs 290 Search conversions is suspicious, may be micro-conversion inflation |
| MacKenzie-Childs | ecommerce / software | ecommerce | luxury_home_goods | Luxury home furnishings/decor, $21.3x ROAS |
| Medley | ecommerce / home_goods | ecommerce | furniture | Modular sofas, $7.1x ROAS — correct type, wrong vertical |
| Mercola Market | ecommerce / pets | ecommerce | health_supplements | Dr. Mercola's supplement/health product store, $4.7x ROAS |
| Prep For Success Tutors | ecommerce / pets | lead_gen | education / tutoring | $228 CPA, 0.7x ROAS = lead gen for tutoring services |
| TRUFIT Customs | ecommerce / pets | ecommerce | automotive_accessories | Custom truck accessories, $2.5x ROAS |
| Tax Helpers new | lead_gen / legal | lead_gen | tax_services | $606 CPA, 1.1x ROAS = tax resolution lead gen |
| The Cover Guy - TCG Wellness | ecommerce / automotive | ecommerce | hot_tub_covers | Hot tub covers + wellness products, $18.2x ROAS |

**The "pets" bug:** The classifier likely matched on a keyword or category that doesn't exist in these accounts. This needs to be traced and fixed in the classify_accounts() method before running on all 454 accounts.

**LOCKLY red flag:** 26,341 PMax conversions vs. 290 Search conversions in the same account. PMax is almost certainly counting micro-conversions (page views, add to carts) as conversions. This is exactly the conversion misconfiguration detector in action — but it wasn't caught because the detector checks for duplicate primaries, not for PMax-specific conversion inflation. This is a missing detection pattern.

---

## 2. Unclassified Account Clusters (433 accounts)

From account names alone, clear vertical clusters emerge:

**Pools, Spas & Hot Tubs (17+ accounts):**
Advance Solar & Spa, Advanced Spas & Pools, All Seasons Pools & Spas, Aqua-Tech, Aquatica Pools & Spas, Champagne Spas, Fox Valley Pool & Spa, Galaxy Home Recreation, Great Bay Spa, Imagine Backyard Living, Le Dipping Parlor Spas, Luxe Outdoor Living, Parnell Pool & Spa, Phoenix Hot Tubs & Swim Spas, Spa Palace, The Sundance Spa and Sauna Store, Waco Pool & Spa, WCI Pools and Spas

→ Business type: local_services. Vertical: pool_spa. Likely lead gen (phone calls, form fills, store visits). This is the largest single-vertical cluster — big enough for intra-vertical pattern detection.

**Beauty, Skincare & Cosmetics (12+ accounts):**
AMP Beauty LA, AVYA Skincare, Airelle Skincare, Aliis Beauty, BioLift, CelleRx, Developlus - Color Oops, Formawell Beauty, Gee Beauty US, Keranique, Orcé Cosmetics, Pistache Skincare

→ Business type: ecommerce. Vertical: beauty_skincare.

**Food & Beverage (12+ accounts):**
Absinthia's Bottled Spirits, Atay Tea, Base Culture, Bulk Box Foods, BulkeCandy, Caliwater, Freestyle Snacks, Green Foods, Intelligentsia Coffee, Kettl Tea, Matchaful, Super Snack Time, What a Crock Meals, Zankou Chicken

→ Mix of ecommerce (packaged goods) and local_services (Zankou Chicken). Vertical: food_beverage.

**Apparel & Fashion (15+ accounts):**
89th and Madison, Banks Journal, Beachgold Bali, Brax, CLOAK Brand, Crazy Shirts, Flying Colors Apparel, Gents, Honey Birdette (US/UK/EU/AU), King Ice, Kivari, Planet Blue, Rave Bae Couture, Slink Jeans, VIGOSS USA, Vetta

→ Business type: ecommerce. Vertical: apparel.

**Medical & Healthcare (10+ accounts):**
Austin Plastic Surgeons, Baumholtz Dr. Michael, H/K/B Cosmetic Surgery, H&W with HBOT, Mark D. Epstein MD, MaxiVision, Noctrix, On-Callrx, Organic Conceptions, Remmie Health, SPEAR Physical Therapy, Thrive Telehealth

→ Business type: lead_gen (mostly). Vertical: healthcare.

**Museums, Nonprofits & Grants (10+ accounts):**
BHAKTI MARGA, CAST Inc - Google Ad Grant, CureDuchenne (x2), Getty Trust (Paid + Grant), Getty Store, LACMA (Grant + Store), Natural History Museum LA (Paid + Grant), Open To Hope, Skirball, Sinai Temple, Spruce Peak Arts

→ Business type: nonprofit. Vertical: arts_culture. Note: Grant accounts use Google Ad Grants ($10K/month free) with different rules and should be flagged.

**Education (5+ accounts):**
Blueprint LSAT, Blueprint Learning, Hudson Children's Academy, Options For Youth, Pathways In Education, Pillar Learning, Star Kids Academy

→ Mix of lead_gen (test prep, private schools) and ecommerce (online courses).

**Real Estate (4+ accounts):**
Elder Group Tahoe, Hall Arts Residences, Neil Leonard Real Estate, Starpoint Properties, Parkway Villas Apartments

→ Business type: lead_gen. Vertical: real_estate.

**Legal (3+ accounts):**
Cooney & Conway, Law Office of Brandon White, Tax Helpers new

→ Business type: lead_gen. Vertical: legal.

**Home Improvement / Construction (5+ accounts):**
Abraham Building, Azure Printed Homes (x2), Blue Horse Construction, Garage Base Systems, Martino Roofing

→ Business type: lead_gen. Vertical: home_improvement.

**Funko Europe (30 accounts):**
Funko - Austria through Funko - Switzerland, Funko - UAE, Funko - UK, Funko App + GMB, Loungefly, Loungefly EMEA

→ All ecommerce / collectibles. Should be tagged as the same parent brand for cross-geography analysis.

---

## 3. Missing Detectors (Found from Audit Checklist Research)

Cross-referencing our 21 detectors against the 80-100+ point audit checklists published by Digital Applied, GROAS, Ryze, and Jelisavac reveals these gaps:

### Missing — Can detect from Google Ads data alone:

**3.1 Search Terms Waste Detection**
- Pull the search_term_view: find high-cost, zero-conversion search terms
- The #1 finding in professional audits: irrelevant search terms waste 15-30% of budget
- Detection: search terms with $15+ spend and 0 conversions in 30 days
- We have keyword data but NOT search terms data yet — needs to be added to ingestion
- Source: every audit checklist lists this as top priority

**3.2 Device Performance Split**
- Mobile vs. desktop CVR gap is one of the most consequential variables
- Mobile accounts for 65% of clicks but only 47% of conversions
- Detection: compare mobile vs. desktop CPA/CVR per campaign. Flag campaigns where mobile CPA is >2x desktop CPA with no bid adjustment
- Data available: daily_metrics can be segmented by device in the API
- Source: Digital Applied benchmarks — mobile CPC 24% lower but CVR 35% lower

**3.3 Geographic Performance Outliers**
- Campaigns targeting multiple regions where some regions have significantly worse CPA
- Detection: compare CPA by geo segment within a campaign. Flag geos with CPA >2x the campaign average
- Data available: geographic_view in the API
- Important for the pool/spa cluster (local businesses with radius targeting)

**3.4 Day/Hour Performance Analysis**
- B2B accounts should pause or reduce bids on weekends. Ecommerce may peak Thursday-Sunday
- Detection: compare conversion rate by hour and day of week. Flag campaigns running 24/7 with clear dead zones
- Data available: ad_schedule segment in campaign reporting

**3.5 Search Partners Performance**
- Search Partners is enabled by default and often produces worse performance
- Detection: flag campaigns where Search Partners is enabled and has >20% of spend with CPA >2x the Search-only CPA
- Data available: network segment in campaign reporting
- Source: Digital Applied and GROAS both flag this as a common default that drains budget

**3.6 Budget Allocation Efficiency**
- The ratio of budget share to conversion share per campaign
- Detection: campaign gets 30% of budget but produces only 5% of conversions = misallocation
- This is different from budget_limited (which checks if a campaign could spend more) — this checks if the budget is going to the right campaigns
- Source: GROAS 15-point checklist, every audit framework

**3.7 RSA Ad Strength Distribution**
- Google rates RSA strength as Poor, Average, Good, Excellent
- Detection: flag campaigns where the majority of RSAs are "Poor" or where ad groups have fewer than the recommended 15 headlines and 4 descriptions
- Data available: ad_group_ad.ad_strength in the API
- We track extension/asset coverage but not RSA health specifically

**3.8 Conversion Counting Type Check**
- "Every" counting (counts repeat conversions) vs. "One" counting (one per click)
- Ecommerce should use "Every" (multiple purchases matter). Lead gen should use "One" (duplicate form fills are noise)
- Detection: lead gen accounts using "Every" counting are inflating conversion numbers
- Data available: conversion_action.counting_type — we already ingest this but don't check business_type alignment

**3.9 Remarketing / Audience List Health**
- Remarketing converts 3-5x better than cold traffic
- Detection: flag accounts with no remarketing campaigns, no audience lists, or audience lists below minimum size (1,000 for Search, 100 for Display)
- Data available: user_list resource in the API

**3.10 PMax Conversion Inflation**
- PMax campaigns counting micro-conversions (page views, add to cart, begin checkout) as primary conversions inflate ROAS and make PMax look artificially strong vs. Search
- Already found this in LOCKLY: 26K PMax conversions vs. 290 Search conversions
- Detection: compare conversion types between PMax and Search campaigns in the same account. If PMax is counting actions that Search isn't, flag the discrepancy
- This is different from duplicate_primary_conversions — it's about PMax specifically inheriting ALL primary actions while Search campaigns may be scoped to specific ones

**3.11 Attribution Model Consistency**
- Accounts switching from last-click to data-driven attribution see apparent performance shifts that aren't real
- Detection: check if attribution model changed recently (in change history). If so, flag that recent performance comparisons may be misleading
- Data available: conversion_action.attribution_model + change_event for changes

### Missing — Cannot detect from Google Ads alone (document as future gaps):

- Landing page speed / mobile usability
- Landing page message match to ad copy
- Competitor ad copy and strategy
- Cross-channel attribution and incrementality
- CRM lead quality downstream of conversion
- Product pricing changes affecting conversion rate
- Organic search ranking changes

---

## 4. Benchmark Data for Vertical Comparison

From Digital Applied, Ryze/WordStream, and Triple Whale 2026 benchmark reports:

### Search Campaign Benchmarks by Vertical

| Vertical | Avg CPC | Avg CTR | Avg CVR | Avg CPA | Notes |
|----------|---------|---------|---------|---------|-------|
| Legal Services | $6.75 | 4.24% | 7.1% | $95 | Highest CPC, but high CVR compensates |
| Insurance | $6.22 | 5.10% | 5.2% | $120 | |
| Dental / Medical | $5.62 | 5.30% | 5.8% | $97 | |
| Home Improvement | $5.21 | 4.80% | 4.5% | $116 | Includes pool/spa cluster |
| B2B / SaaS | $3.33 | 2.09% | 3.8% | $88 | Low CTR, long sales cycle |
| Education | $3.12 | 5.50% | 5.3% | $59 | |
| Finance / Banking | $3.08 | 5.70% | 5.5% | $56 | |
| Real Estate | $2.81 | 7.40% | 3.4% | $83 | High CTR, low CVR |
| Technology | $2.62 | 2.09% | 3.0% | $87 | |
| Automotive | $2.46 | 7.93% | 6.0% | $41 | Includes auto accessories |
| Fitness / Recreation | $1.90 | 5.70% | 5.1% | $37 | Includes golf |
| Food / Restaurant | $1.84 | 7.60% | 5.2% | $35 | |
| Travel / Hospitality | $1.63 | 8.50% | 4.7% | $35 | |
| Retail / Ecommerce | $1.16 | 6.60% | 3.1% | $37 | General ecommerce |
| Arts / Entertainment | $0.63 | 13.10% | 5.0% | $13 | Museums, events |

### Cross-Network Benchmarks (2026)

| Network | Avg CPC | Avg CTR | Avg CVR | Avg CPA |
|---------|---------|---------|---------|---------|
| Search | $2.96 | 3.52% | 4.40% | $53.89 |
| Display | $0.44 | 0.39% | 0.72% | $61.11 |
| Shopping | $0.58 | 0.86% | 1.90% | $30.53 |
| Video (YouTube) | $0.18 | 0.65% | 1.12% | $16.07 |
| PMax (blended) | $1.25 | 1.20% | 2.80% | $44.64 |

### Key Benchmark Insights for BrightMatter

- CTR improved across ALL industries in 2025-2026, driven by better RSA optimization and AI creative
- CVR declined across 13 of 14 industries — rising CTR + falling CVR suggests a gap between ad promise and landing page delivery
- ROAS declined across 13 of 14 industries, mirroring the CVR pattern
- CPC rose 12% YoY cross-industry average — CPC inflation is accelerating
- Quality Score 8-10 accounts pay 37% less CPC than median. QS 4 or below pay 64% more
- Smart Bidding accounts report 22% lower CPA vs manual CPC, but varies by maturity
- 78% of spend now runs through Smart Bidding or PMax

---

## 5. Ingested Account Performance vs. Benchmarks

Comparing the 21 ingested accounts against vertical benchmarks:

**Outperforming benchmarks:**
- VICI (apparel): $15 CPA vs $37 benchmark, 8.3x ROAS — strong
- MacKenzie-Childs (luxury home): $12 CPA, 21.3x ROAS — very strong but may have brand ROAS inflation
- Coway (home appliances): $15 CPA, 16.1x ROAS — significantly outperforming
- The Cover Guy (hot tub covers): $44 CPA, 18.2x ROAS — niche dominance
- APL (footwear): $38 CPA, 8.4x ROAS — strong for premium footwear

**At benchmark:**
- Funko (collectibles): $6 CPA, 3.3x ROAS — healthy volume play
- Mercola Market (supplements): $24 CPA, 4.7x ROAS — reasonable for health supplements
- Medley (furniture): $113 CPA, 7.1x ROAS — high CPA but high AOV product justifies it
- TRUFIT Customs (auto accessories): $46 CPA, 2.5x ROAS — marginal

**Underperforming or flagged:**
- Tax Helpers (tax services): $606 CPA, 1.1x ROAS — legal/tax CPAs are high but this is extreme. Needs LTV analysis
- Prep For Success (tutoring): $228 CPA, 0.7x ROAS — underwater on last-click. Either lead quality is very high downstream or this is losing money
- Hawke Media Internal: $580 CPA, 3.6x ROAS — agency lead gen, high CPA is normal if deal sizes are large
- BMS Moving (moving services): $124 CPA, 0.8x ROAS — conversion value may not reflect actual job revenue
- Corwin Master CID: $213 CPA, 0.3x ROAS — multi-brand container, likely mixed signals
- LOCKLY: $8 CPA, 5.1x ROAS — looks amazing but 26K PMax conversions are almost certainly micro-conversions, not purchases. Real CPA is likely 10-50x higher

---

## 6. Summary: What's Missing from the Foundation

### Classification (blocking everything downstream)
- 433 of 454 accounts unclassified
- 21 classified accounts have wrong verticals (the "pets" bug)
- Fix: correct the 21, run heuristic classifier on 433, flag ambiguous for manual review

### Missing detectors (11 gaps found)
- 3.1 Search terms waste — **highest priority**, needs search_term_view in ingestion
- 3.2 Device performance split — high priority, easy to add
- 3.3 Geographic outliers — high priority for local services cluster
- 3.4 Day/hour analysis — medium priority
- 3.5 Search Partners check — medium priority, quick win
- 3.6 Budget allocation efficiency — high priority
- 3.7 RSA ad strength — medium priority
- 3.8 Conversion counting type alignment — medium priority, data already ingested
- 3.9 Remarketing/audience health — medium priority, needs new API pull
- 3.10 PMax conversion inflation — **critical**, already found in LOCKLY
- 3.11 Attribution model consistency — medium priority

### Existing detector improvements needed
- Harnesses for 11 of 21 detectors still missing
- 5 REVISE detectors have threshold configs but not yet wired to code
- brand_nonbrand detector needs classification fix before it's meaningful

### Benchmark integration
- No benchmarks embedded in thresholds yet
- Detectors should compare against vertical-specific benchmarks, not just account history
- The benchmark data above should be added to thresholds.yaml as vertical baselines
