# BrightMatter Agent Briefs: Research → Discovery → Build

*Two parallel workstreams. Research agents study the experts and patterns. Coding agents explore what's in the 500 accounts. Research findings inform engineering decisions.*

---

## Workstream A: Research Agents

Use the three reference docs:
- `brightmatter-google-ads-signal-map.md` — features, configurations, external signals, ingestion tiers
- `brightmatter-pattern-research-map.md` — 12 pattern domains with known patterns and sources
- `brightmatter-research-brief-experts-and-causal-chains.md` — 16 experts, 12 causal chains

---

### A1: Expert Framework Research

**For each Tier 1 expert (Geddes, Kirk Williams, Vallaeys, McNair/smec, Rhodes, Lolk):**

Go find their published work. Read it. For each expert, come back with:

1. What is their core framework or methodology? Not their opinions — their *system* for evaluating and optimizing Google Ads accounts.
2. What specific patterns do they say matter most? (e.g., "Kirk Williams says X about Shopping feed structure correlating with Y outcome")
3. What data points would you need to detect those patterns automatically? This is the critical output — it tells the coding agents what to pull from the API.
4. What do they say about cross-account patterns specifically? Anything about how patterns differ by vertical, spend level, account maturity?
5. What do they say is commonly misdiagnosed or overlooked?

**Priority sources per expert (start here, expand if needed):**
- Geddes: AdAlysis blog, *Advanced Google AdWords* book, SMX presentations
- Kirk Williams: ZATO blog, Optmyzr interview, his Twitter/X threads on Shopping vs PMax
- Vallaeys: Optmyzr blog, *Unlevel the Playing Field*, his Google Marketing Live commentary
- McNair/smec: smarter-ecommerce.com/blog — specifically the PMax Campaign Orchestration series
- Rhodes: AgencySavvy content, Google Ads Scripts repositories, his agency workflow content
- Lolk: SavvyRevenue blog, his Shopping and ecommerce PPC guides

**For each Tier 2 expert (Jyll, Navah, Ameet, Reva, Amy Hebdon, Chris Ridley):**

Same questions but lighter — focus on their contrarian takes and any specific data they've published. 1-2 key pieces per expert, not a deep dive.

**For Tier 3 sources (ALM Corp, Tinuiti, Merkle, WordStream):**

Pull their actual benchmark data. We need numbers:
- CPC by vertical (search, shopping, display)
- CTR by campaign type and vertical
- CVR by vertical and funnel stage
- CPA/ROAS benchmarks by vertical
- Any cross-account trend data (QoQ or YoY)

These become BrightMatter's baseline — what "normal" looks like before we can detect "abnormal."

---

### A2: Pattern Detection Research

**For each of the 12 pattern domains in the Pattern Research Map:**

Go deeper on the sources listed. For each domain, come back with:

1. What are the specific, measurable patterns? Not "branded search matters" but "branded CPC rises X% when Auction Insights overlap increases Y%" — the quantified version.
2. What are the thresholds? When does a signal become actionable? (e.g., "Quality Score below 5 on keywords with >$100/month spend is worth investigating")
3. What's the minimum data needed to detect this pattern reliably? How many accounts, how many days of data, what sample size?
4. How does this pattern differ by segment? Does it behave differently for ecommerce vs. lead gen, high spend vs. low spend, Search vs. PMax?
5. What's the detection logic? If you were writing a SQL query or a Python function to detect this pattern across 500 accounts, what would the logic be?

Output #5 is what feeds directly into the coding agents' work. The research should produce detection logic descriptions that a coding agent can implement.

---

### A3: Causal Chain Research

**For each of the 12 external cause → effect chains in the Research Brief:**

Go find real-world case studies or documented examples. For each chain, come back with:

1. What does this look like in actual Google Ads data? Specific metrics, specific patterns, specific timeframes.
2. How do you distinguish this from an account-level problem? What's the diagnostic test?
3. How quickly does the effect manifest after the cause? (hours, days, weeks?)
4. What's the correct response vs. the common wrong response?
5. Are there any automated detection methods published? (Scripts, rules, tools that already detect this)

---

### A4: What Research Should Answer for Engineering

The research agents' work should ultimately answer these questions for the coding agents:

**Account taxonomy:**
- What are the right segmentation dimensions? (Research should tell us: vertical matters because X, spend tier matters because Y, campaign type mix matters because Z)
- What are the segment boundaries? (e.g., "accounts below $5K/month behave differently from accounts above" — what's the actual threshold?)

**Ingestion priority:**
- Which fields from the API actually matter for pattern detection? (Research should narrow the 200+ available fields down to the 20-40 that expert frameworks say drive decisions)
- What granularity matters? (Daily vs. weekly, campaign-level vs. keyword-level, account-level vs. ad-group-level)

**Episode schema:**
- What constitutes an "episode" for BrightMatter? (Research should identify: these are the decisions agencies make, this is what the before/after state looks like, this is how outcomes should be measured)

**Baseline and anomaly thresholds:**
- What are normal ranges for key metrics by segment? (Research should provide the benchmark data)
- What magnitude of change constitutes an anomaly worth flagging? (Research should provide threshold guidance from expert frameworks)

---

## Workstream B: Coding Agents

Start these tasks in parallel with the research. These are exploration tasks — discover what's there and report back. Don't build anything permanent yet.

**Reference docs:** Use these to guide what you look for and how to access it.

*Our docs (what to look for):*
- `brightmatter-google-ads-signal-map.md` — Part 1 lists every feature/configuration by hierarchy level (account → campaign → ad group → keyword → ad → shopping feed). Part 3 maps ingestion priority tiers. Use this as your checklist when exploring what's in each account.
- `brightmatter-pattern-research-map.md` — 12 pattern domains describe what we're ultimately trying to detect. When you're exploring data, keep asking: "Is the data I'm seeing sufficient to detect these patterns?"
- `brightmatter-research-brief-experts-and-causal-chains.md` — Section 2 describes 12 external cause → effect chains. Several of these (tracking breaks, auto-applied recommendations, conversion definition changes) are detectable from inside the Google Ads API. Look for evidence of these while exploring.

*Google Ads API docs (how to access it):*
- **Start here — API overview and concepts:** https://developers.google.com/google-ads/api/docs/start
- **GAQL (Google Ads Query Language) — how to query everything:** https://developers.google.com/google-ads/api/docs/query/overview
- **GAQL interactive query builder:** https://developers.google.com/google-ads/api/fields/v19/overview
- **Resource reference (every queryable entity):** https://developers.google.com/google-ads/api/fields/v19/overview_query_builder
- **Campaign management:** https://developers.google.com/google-ads/api/docs/campaigns/overview
- **Bidding strategies:** https://developers.google.com/google-ads/api/docs/campaigns/bidding/assign-strategies
- **Targeting and audiences:** https://developers.google.com/google-ads/api/docs/targeting/overview
- **Performance Max reporting:** https://developers.google.com/google-ads/api/performance-max/reporting
- **AI Max for Search reporting:** https://developers.google.com/google-ads/api/docs/campaigns/ai-max-for-search-campaigns/ai-max-reporting
- **Shopping campaigns:** https://developers.google.com/google-ads/api/docs/shopping-ads/overview
- **Change History (ChangeEvent resource):** https://developers.google.com/google-ads/api/docs/change-status/overview
- **Keyword Quality Score fields:** https://developers.google.com/google-ads/api/fields/v19/keyword_view
- **Search terms report:** https://developers.google.com/google-ads/api/fields/v19/search_term_view
- **Auction Insights:** https://developers.google.com/google-ads/api/docs/reporting/auction-insights
- **Account hierarchy (MCC):** https://developers.google.com/google-ads/api/docs/account-management/listing-accounts
- **Metrics reference (every available metric):** https://developers.google.com/google-ads/api/fields/v19/metrics
- **Segments reference (every available dimension):** https://developers.google.com/google-ads/api/fields/v19/segments
- **Rate limits and quotas:** https://developers.google.com/google-ads/api/docs/best-practices/quotas
- **Client libraries (Python):** https://developers.google.com/google-ads/api/docs/client-libs/python

Use the GAQL interactive query builder to test queries before writing code. It shows you exactly which fields are available on which resources and which combinations are valid.

**Scope: Google Ads only.** Do not attempt to connect GA4, Google Search Console, or any external data sources in this phase. Everything we need to start pattern recognition is inside the Google Ads API. GA4 and external signals are enrichment layers for later — they help explain *why* something happened, but Google Ads data alone tells us *what* happened, *what changed*, and *what the outcome was*. That's sufficient for the core learning loop.

---

### B0: Company & Client Discovery

**Goal:** Figure out who these 500 accounts actually are. What companies, what industries, what they sell, who their customers are. We can't build patterns by vertical if we don't know the verticals.

**Direction:**
- Start with the MCC hierarchy. Pull every account name, descriptive name, and any labels/tags applied at the MCC level
- For each account, look at campaign names and ad group names — these often contain the company name, product lines, service areas, or brand names (e.g., "Brand - Acme Widgets", "NB - Running Shoes", "PMax - Skincare")
- Pull the final URLs from active ads — the domains tell you what company it is and what they sell. Group accounts by domain. Some companies may have multiple accounts
- For accounts with Shopping campaigns, check the linked Merchant Center — the store name and product categories reveal the business type
- Pull ad copy (headlines and descriptions) from active RSAs — the language reveals what the business does and what they sell
- Check for any account-level labels, notes, or custom attributes that indicate client name, vertical, or account manager

**Classification task:**
For each account, try to determine:
- Company/client name
- Website URL
- Business type: ecommerce, lead gen, SaaS, local services, B2B, marketplace, app, other
- Vertical/industry: if ecommerce, what category (apparel, beauty, supplements, home goods, electronics, food/beverage, etc.). If lead gen, what industry (legal, medical, home services, financial, education, etc.)
- Approximate size: infer from spend level and website (small business, mid-market, enterprise)
- Business model clues: subscription vs. one-time purchase, high-ticket vs. low-ticket, local vs. national vs. international

**What to look for in the data that reveals the business:**
- Conversion action names (e.g., "Purchase", "Lead Form Submit", "Phone Call", "Book Appointment", "Schedule Demo" — each reveals the business model)
- Conversion values (if set, reveal average order value or lead value)
- Geographic targeting (local radius = local business, national = ecommerce/SaaS, international = larger brand)
- Language targeting (multi-language = international)
- Ad schedule (B2B often pauses weekends, ecommerce runs 24/7, local services may have business hours)

**Report back:**
- A complete account roster: account ID, company name (best guess), website, business type, vertical, spend level
- How many distinct companies vs. how many accounts (some companies may have multiple accounts)
- Vertical distribution: how many ecommerce, how many lead gen, how many B2B, etc.
- Any accounts you can't classify — flag these for manual review
- Any interesting clusters (e.g., "15 accounts are all dental practices in Texas", "30 accounts are all DTC skincare brands")
- Which accounts are clearly the most active and valuable vs. which are dormant or test accounts

This is the foundation for everything. Patterns are only meaningful within segments. If we don't know the segments, we can't build patterns.

---

### B1: Account Profile & Structure Deep Dive

**Goal:** For every active account, get a detailed profile of what's inside it — campaign structure, configuration state, and performance baseline.

**Reference:** Use Part 1 of `brightmatter-google-ads-signal-map.md` as your checklist. It lists every configuration at every level (campaign, ad group, keyword, ad, shopping feed). Walk through the hierarchy and document what exists.

**Direction:**
- For each account, pull ALL campaigns with their full configuration:
  - Campaign type (Search, PMax, Shopping, Display, Video, Demand Gen, App)
  - Campaign status (enabled, paused, removed — and when it was last active)
  - Bidding strategy (type + target values if applicable)
  - Budget (daily amount, shared vs. individual)
  - Network settings (Search Partners enabled? Display expansion?)
  - Geographic targeting (countries, regions, radius)
  - Ad schedule (any day/time restrictions)
  - Brand exclusions (for PMax)
  - Conversion goals (which conversion actions are the campaign optimizing for)
- For Search campaigns specifically:
  - Number of ad groups and their themes
  - Keyword count and match type breakdown (broad, phrase, exact)
  - Negative keyword count (campaign-level and shared lists)
  - RSA count and ad strength distribution
  - Extension/asset coverage (sitelinks, callouts, structured snippets, images, etc.)
- For PMax campaigns specifically:
  - Number of asset groups
  - Search themes count and what they contain
  - Audience signals present (customer lists, in-market, custom segments)
  - Whether Merchant Center feed is connected
  - Final URL expansion settings
- For Shopping campaigns:
  - Product group structure
  - Feed quality (disapprovals, warnings)
  - Custom label usage
- Count total active keywords, total active ads, total conversion actions per account

**Report back:**
- Per-account profile cards (structured data: campaign count by type, keyword count, spend, primary bidding strategy, conversion tracking health)
- Cross-account aggregates: what does the "average" account look like? What does the "best" account look like? What does the "worst" account look like?
- Configuration patterns: are most accounts set up similarly (suggesting a template was used) or are they wildly different?
- Structural health indicators: accounts with single-campaign structures vs. well-segmented accounts, accounts with no negative keywords, accounts with no extensions, accounts with broken conversion tracking
- Per the Pattern Research Map domains: is there enough Search campaign data to detect branded vs. non-branded patterns? Enough PMax data? Enough Shopping data? Which pattern domains are feasible with this data vs. which lack sufficient accounts?

---

### B2: Historical Data & Performance Archaeology

**Goal:** Figure out what historical data exists, how deep it goes, and what it tells us about performance over time. This is our training data for BrightMatter — the more history, the more patterns.

**Reference:** The Pattern Research Map describes 12 pattern domains. Several require historical data to detect (seasonal patterns need YoY data, bidding strategy patterns need pre/post transition data, creative fatigue needs weekly performance trends). Check what's available against what the patterns need.

**Direction:**
- For a sample of ~20 accounts (pick 5 high-spend, 5 mid-spend, 5 low-spend, 5 varied campaign types), pull performance data going as far back as the API allows
- Pull at multiple granularities: daily campaign-level, weekly ad-group-level, monthly keyword-level. How far back does each go?
- Pull historical Quality Score data — does it exist? How far back? At what granularity?
- Pull Auction Insights data — does it go back more than 30 days? What competitors appear?
- Pull search terms reports — how far back, what volume, how detailed?
- Check for historical conversion tracking data — have conversion actions changed over time? Can you see the history of conversion definitions?
- Look for performance inflection points in the historical data — sudden jumps or drops that might correspond to strategy changes, seasonal patterns, or external events (these are proto-episodes)

**Report back:**
- Data depth by account: how many months/years of usable data per account
- Data richness map: which metrics are available historically and which only exist for recent periods
- Quality Score history availability — this is critical for pattern domain #2 (non-branded search patterns)
- Historical performance profiles: for the sampled accounts, what does the performance trajectory look like? Growing, declining, stable, volatile?
- Any obvious seasonal patterns visible in the historical data
- Any "events" visible in the data — sudden changes that could be tracked back to causes
- An honest assessment: how much historical data do we actually have to bootstrap BrightMatter's learning, vs. how much will we need to collect going forward?

---

### B3: Configuration Landscape & Health Audit

**Goal:** Map the configuration state across all 500 accounts and identify patterns, anti-patterns, and health issues. Cross-reference with B0 (company discovery) to see if configuration patterns correlate with verticals or business types.

**Reference:** The Signal Map Part 1 lists every possible configuration. The Pattern Research Map Section 7 (Campaign Structure Patterns) and Section 6 (Bidding Strategy Patterns) describe what "good" and "bad" structures look like. The Research Brief Section 2.11 describes auto-applied recommendations as a causal chain — look for evidence of these.

**Direction:**
- For ALL accounts, pull campaign-level configurations: bidding strategy type, budget, network settings, targeting settings, conversion goals
- Aggregate: what % of campaigns use tCPA vs. tROAS vs. Maximize Conversions vs. Maximize Clicks vs. manual? Break this down by campaign type AND by vertical (from B0)
- For Search campaigns: pull match type distribution. What % of accounts are still running all exact match? What % have adopted broad + Smart Bidding? Does this correlate with performance?
- For PMax campaigns: asset group count, search theme count, audience signal presence, brand exclusion status, final URL expansion settings. How many PMax campaigns are running "naked" (no audience signals, no search themes, default everything)?
- For Shopping: Merchant Center link status, feed quality (disapprovals, warnings, item count), custom label usage
- Check conversion tracking per account:
  - How many conversion actions exist?
  - What types? (purchase, lead, call, page view, import, etc.)
  - Primary vs. secondary designation — are accounts optimizing for the right thing?
  - Attribution model in use (last click vs. data-driven)
  - Any accounts with suspicious tracking (e.g., page views as primary conversions, zero conversion value set)
- Check for auto-applied recommendations: pull recommendation history if available, look for changes in change history that weren't made by a named human user
- Check extension/asset coverage: what % of accounts have sitelinks, callouts, structured snippets, images, etc.? What's missing?
- Look at geographic targeting: how many accounts target locally vs. nationally vs. internationally? Does this match the business type from B0?

**Report back:**
- Full configuration census: percentages for every major setting across all accounts
- Configuration vs. vertical cross-tab: do ecommerce accounts look different from lead gen accounts? How?
- Configuration vs. spend cross-tab: do high-spend accounts have better structure than low-spend?
- Anti-pattern detection: flag specific misconfigurations (Search Partners enabled without monitoring, PMax without audience signals, all-exact-match with tCPA bidding, page views as primary conversion, etc.)
- Conversion tracking health score per account: clean, messy, or broken
- Auto-applied recommendation evidence: how many accounts show signs of Google making changes without human approval?
- A ranked list of accounts by "configuration health" — which are well-structured and which need intervention?
- Cross-reference everything with the B0 company roster — do patterns emerge by company type?

---

### B4: Change History Exploration

**Goal:** The Change History is the single most important data source for BrightMatter's learning loop. Explore it thoroughly.

**Direction:**
- For a sample of ~10 active accounts with recent changes, pull the full Change History for the last 90 days
- Document: what change types are recorded (bid changes, budget changes, keyword additions/removals, status changes, ad copy changes, targeting changes, conversion tracking changes)
- Check: are auto-applied recommendations distinguishable from human changes?
- Check: does the Change History include "before" and "after" values, or just "something changed"?
- Check: can you correlate a specific change with performance data on the days before and after the change?
- Check: what's the volume of changes? Are some accounts getting 5 changes/month and others 500?

**Report back:**
- What the Change History actually contains (exact fields, granularity, attribution)
- Whether before/after values are available (critical for episode recording)
- Whether auto-applied vs. human changes are distinguishable
- Volume and frequency of changes across accounts
- An honest assessment: is Change History rich enough to serve as BrightMatter's primary episode source, or do we need to supplement it?
- Sample data showing what a "change → outcome" pair looks like in real data

---

### B5: Rate Limits & Feasibility

**Goal:** Figure out if we can actually pull data from 500 accounts on a daily/weekly cadence without hitting API limits.

**Direction:**
- Check the Google Ads API rate limits for your developer token level (Basic vs. Standard access)
- Estimate the number of API calls needed to pull Tier 1 data (campaign-level daily metrics) for all 500 accounts
- Test parallel request patterns — how many accounts can you query simultaneously?
- Time how long a full account pull takes for one account, then extrapolate to 500
- Check if there are any accounts that are abnormally large (thousands of campaigns) that would need special handling

**Report back:**
- Estimated total API calls per daily ingestion cycle
- Estimated total time for a full 500-account daily pull
- Any rate limit issues encountered
- Recommended batch strategy (parallelism level, request spacing)
- Whether this is feasible on Modal's free/starter tier or needs more compute

---

## How the Workstreams Connect

```
Research A1 (Expert Frameworks)
  → Tells coding agents which API fields matter most
  → Informs the account taxonomy dimensions

Research A2 (Pattern Detection)
  → Tells coding agents what detection logic to build
  → Defines what granularity of data is needed

Research A3 (Causal Chains)
  → Tells coding agents what external data sources to connect LATER (not in initial build)
  → Defines the diagnostic hierarchy (check tracking first, then macro, then account)
  → Some causal chains ARE detectable from Google Ads alone (tracking breaks, auto-applied recs, competitor changes via Auction Insights, conversion definition changes)

Research A4 (Synthesis)
  → Produces the schema decisions: episode format, segmentation spec, baseline thresholds

Coding B0 (Company & Client Discovery)
  → Tells everyone who these accounts actually are
  → Defines the real segments (not theoretical verticals — actual verticals in the data)
  → Feeds back to research agents: "we have 80 ecommerce, 200 lead gen, 50 B2B — prioritize patterns for those"

Coding B1 (Account Profile & Structure)
  → Reveals what's actually in each account
  → Cross-referenced with B0, shows configuration patterns by business type
  → First raw material for pattern recognition (before any learning system exists)

Coding B2 (Historical Data & Performance)
  → Tells everyone what's actually possible vs. theoretical
  → Shows how much training data exists for BrightMatter to learn from
  → May reveal historical patterns (seasonal, structural) visible in raw data

Coding B3 (Configuration Landscape & Health)
  → Maps every configuration across 500 accounts
  → Cross-referenced with B0 + performance data, reveals which configurations work for which segments
  → Identifies immediate optimization opportunities (misconfigurations)

Coding B4 (Change History)
  → Validates or invalidates the episode-from-change-history approach
  → Determines whether we need an alternative episode source

Coding B5 (Rate Limits & Feasibility)
  → Sets the engineering constraints for everything else
```

**After both workstreams report back, we converge on:**
1. Account taxonomy (informed by A1 + A4 + B0 + B1 + B3)
2. Ingestion schema (informed by A1 + A2 + B1 + B2 + B4)
3. Episode format (informed by A2 + A4 + B4)
4. Detection logic specs (informed by A2 + A3 + B3)
5. Engineering architecture (informed by B2 + B5)
6. Immediate wins — misconfigurations and anti-patterns from B3 that can be fixed now, before BrightMatter even exists

Then we build.
