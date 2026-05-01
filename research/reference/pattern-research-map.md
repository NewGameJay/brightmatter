# BrightMatter Pattern Research Map

*What patterns exist, what BrightMatter should learn to detect, and where to go deeper — organized by campaign type and decision domain.*

---

## 1. Branded Search Patterns

**Core pattern:** Brand campaigns aren't growth levers — they're control layers. The pattern BrightMatter needs to learn is *when brand defense is worth the spend vs. when it's cannibalizing organic clicks you'd get anyway*.

**Known patterns to detect:**
- Brand CPC creep: competitors bidding on your brand terms drives up your brand CPC. Track Auction Insights overlap rate on brand terms over time — rising competitor presence = rising brand CPCs
- Brand/non-brand ROAS contamination: blended account ROAS looks healthy but is entirely carried by cheap brand conversions. Non-brand is actually underwater. BrightMatter should always separate brand vs. non-brand performance
- PMax brand leakage: PMax campaigns absorb brand traffic when brand exclusions aren't active, inflating PMax ROAS and starving the dedicated brand campaign. Pattern: PMax ROAS drops when brand exclusions are added = it was riding on brand intent
- Incrementality test patterns: accounts that pause brand campaigns and see <15% traffic loss to organic = brand spend is largely defensive, not incremental
- Brand campaign structure: exact match brand terms with high-intent segments (pricing, reviews, demo) routed to specific landing pages outperform single catch-all brand ad groups

**Research deeper:**
- VIDEN: "The Impact of Branded vs Non-Branded Bidding in PPC Search Ads" (videnglobe.com/blog/branded-vs-non-branded-keywords) — 150+ account audit data on brand/non-brand separation
- PPC Pitbulls: Brand vs Non-Brand Results separation (ppcpitbulls.com/blog/why-you-need-to-separate-brand-and-non-brand-results-in-google-ads)
- Google Ads Help: Cross-account conversion tracking for consistent brand measurement

---

## 2. Non-Branded Search Patterns

**Core pattern:** Non-brand Search is the true growth engine but operates under fundamentally different economics. The key learning is *which keyword strategies produce profitable growth at different spend levels*.

**Known patterns to detect:**
- Match type migration curve: accounts that move from exact-only to broad+Smart Bidding typically see a 2-4 week performance dip followed by a volume increase. BrightMatter should learn which account profiles (conversion volume, vertical, budget) successfully make this transition vs. which lose efficiency
- Quality Score leverage: keywords with QS 7+ deliver significantly lower CPCs than QS 5-6. The three components (expected CTR, ad relevance, landing page experience) have different weights — landing page experience is the most durable lever
- Keyword lifecycle: new keywords go through a learning phase (2-4 weeks), then stabilize, then may plateau. Detecting keyword fatigue before it becomes a spend problem
- Negative keyword hygiene: the ratio of negative keywords to active keywords correlates with account efficiency. Accounts that review search terms weekly and add negatives systematically outperform those that don't
- Query-to-landing-page alignment: non-brand keywords where the search term, ad copy, and landing page all reference the same specific intent produce 2-3x conversion rates vs. generic routing
- AI Max expansion patterns: Google's AI Max for Search expands keyword matching via website content. Track which expansions produce conversions vs. waste — the pattern differs by vertical

**Research deeper:**
- ALM Corp: "Google Search Ads Audit in 2026" (almcorp.com/blog/google-search-ads-audit-2026/) — the most rigorous framework for evaluating Search account health, marginal CPA analysis, signal architecture
- ALM Corp: "Google Ads Advanced Tactics to Maximize ROAS for 2026" (almcorp.com/blog/google-ads-advanced-tactics-to-maximize-roas-for-2026/) — campaign structure recommendations, match type strategy, first-party data prioritization
- Google Ads API: AI Max reporting and search_term_match_source filtering (developers.google.com/google-ads/api/docs/campaigns/ai-max-for-search-campaigns/ai-max-reporting)
- TwoSquares: Quality Score guide (twosquares.co.uk/blog/google-ads-quality-score-guide) — component-level optimization strategy

---

## 3. Performance Max Patterns

**Core pattern:** PMax is a distribution layer, not a strategy. It amplifies whatever inputs you give it. The learning is *which input configurations produce which outcomes for which account profiles*.

**Known patterns to detect:**
- Channel spend distribution: healthy ecommerce PMax = 60-80% Shopping spend. If Display/YouTube dominates, the product feed needs work. BrightMatter should flag when channel distribution shifts outside vertical norms
- Conversion signal quality: PMax optimized toward "Begin Checkout" behaves very differently than PMax optimized toward "Purchase." Learning which conversion goal produces the best downstream revenue per vertical/spend level
- Asset group structure: single asset group vs. multiple groups by product category/audience. Pattern: consolidated groups learn faster but can't differentiate messaging. Segmented groups need 30+ conversions/month each to learn effectively
- Search theme effectiveness: which search themes actually drive conversions vs. waste budget. Cross-account patterns by vertical would be extremely valuable
- Brand exclusion impact: before/after analysis when brand exclusions are added to PMax. Typical pattern: ROAS drops 20-40% initially (brand traffic was inflating it) but the remaining ROAS reflects true incremental value
- PMax + Search coexistence: PMax uplift experiments measure whether PMax adds incremental reach or just cannibalizes Search. Pattern varies by account maturity and conversion volume
- Learning period behavior: new PMax campaigns need 2-4 weeks and 50+ conversions to stabilize. Setting tROAS targets too early constrains the algorithm
- Feed optimization leverage: product title structure (Brand + Product Type + Key Attribute) has outsized impact on Shopping visibility within PMax. Custom labels for margin-based segmentation enable profit-aware bidding

**Research deeper:**
- Smarter Ecommerce: "The Ultimate Ecommerce Campaign Optimization Playbook for PMax" (smarter-ecommerce.com/blog/en/ecommerce/the-ultimate-ecommerce-campaign-optimization-playbook-for-pmax/) — 1000+ campaign dataset, Dynamic Segments approach, Campaign Orchestration methodology
- Optmyzr: "How to Optimize Performance Max in 2026" (optmyzr.com/guide/performance-max/) — expert interviews with Jyll Saskin Gales and Kirk Williams on PMax optimization levers
- Store Growers: "Performance Max Campaigns: The Ultimate Ecommerce Guide 2026" (storegrowers.com/performance-max-campaigns/) — practical PMax + Standard Shopping coexistence strategy
- Involve Digital: "Performance Max Optimisation Guide 2026" (involvedigital.com/insights/performance-max-optimisation-guide-2026/) — ROAS benchmarks by industry, bidding maturity progression
- Coby Agency: "Advanced Performance Max Strategies 2026" (cobyagency.com) — PMax Uplift experiments, first-party audience exclusions, channel performance timeline

---

## 4. YouTube / Video Campaign Patterns

**Core pattern:** YouTube is a creative-first channel where the first 5 seconds determine ROI. The learning is *which creative structures produce view-through and conversion at different funnel stages*.

**Known patterns to detect:**
- Hook framework performance: pattern break hooks vs. hyper-specific promise vs. pain call-out vs. social proof lead vs. curiosity gap. Track VTR (view-through rate) by hook type across accounts/verticals
- 5-second rule: ads that establish brand presence before the skip button see 40% higher VTR. Ads that bury branding at the end underperform
- Format-funnel alignment: 6-second bumpers for awareness, 15-60s skippable for consideration, non-skippable for brand moments. Using the wrong format at the wrong stage wastes budget
- Shorts vs. in-stream creative: purpose-built vertical Shorts creative outperforms reformatted horizontal content by 40-60%. These need different creative strategies entirely
- Creative fatigue velocity: YouTube creative fatigues faster than Search ads. Track performance decay curves by creative type — when does VTR start declining? How many weeks until a refresh is needed?
- Audience signal quality: predictive audiences (likely to purchase within 90 days) converting at 2.3x vs. demographic targeting and 1.8x vs. standard remarketing
- Demand Gen as mid-funnel: Demand Gen campaigns across YouTube + Discover + Gmail behave more like Meta campaigns than traditional Google campaigns. Track which audience/creative combinations drive consideration-stage actions
- Real-time creative optimization: Google now auto-tests video asset combinations. Track which element (hook, body, CTA, format) has the largest impact on performance variance

**Research deeper:**
- Digital Applied: "YouTube Ads 2026: Video Advertising Strategy Guide" (digitalapplied.com/blog/youtube-ads-2026-video-advertising-strategy-guide) — format-by-funnel framework, VTR benchmarks, creative production process
- GROAS: "YouTube Ads Updates: What Changed in Early 2026" (groas.ai/post/youtube-ads-updates-what-changed-in-early-2026) — predictive audiences, real-time creative optimization, Shorts algorithmic targeting
- Creatify: "YouTube Ads: How to Create Video Ads That Convert in 2026" (creatify.ai/blog/youtube-ads-how-to-create-video-ads-that-convert-in-2026) — hook frameworks with examples, creative testing pipeline methodology
- Jetfuel Agency: "YouTube Ads Guide 2026" (jetfuel.agency/youtube-ads-guide-2026/) — DTC-specific YouTube strategy, Funnel Stack Method, Demand Gen deep dive
- AdSpyder: "Top 15 YouTube Advertising Campaigns 2026" (adspyder.io/blog/top-15-youtube-advertising-campaigns-2026/) — creative iteration pipeline (10 hooks → 3 edit styles → format variants → keep top 20%)

---

## 5. Shopping / Product Feed Patterns

**Core pattern:** In ecommerce, the product feed is the campaign. Weak feed = weak results regardless of campaign settings. The learning is *which feed optimizations produce the largest performance lifts by product category*.

**Known patterns to detect:**
- Title optimization impact: front-loading searchable attributes (Brand + Product Type + Key Attribute + Size/Color) in product titles has the single largest impact on Shopping visibility
- Custom label segmentation: products segmented by margin tier, best-seller status, or seasonality into separate campaigns/asset groups outperform flat structures. Learning which segmentation axis matters most per vertical
- Price competitiveness: products priced above competitor average see declining impression share and CTR. Track price position vs. performance correlation
- Stock-out cascading: when a best-selling product goes out of stock, the campaign's overall performance drops disproportionately because the algorithm loses its highest-performing signal
- Image quality correlation: white-background primary images for Shopping, lifestyle images for Display/Discover. Products with multiple high-quality images outperform single-image listings
- Promotional timing: sale price annotations lift CTR. Learning when to use promotions vs. everyday pricing by product category and season
- Supplemental feed enrichment: adding descriptive attributes via supplemental feeds (without touching the primary feed) produces measurable lifts in query matching breadth

**Research deeper:**
- Channable: "Google Performance Campaign (PMAX): Ultimate Guide" (channable.com/blog/performance-max-campaigns) — feed optimization for PMax, custom label strategy, title optimization formulas
- Google Merchant Center documentation — feed specification, diagnostics, competitive visibility reports
- DataFeedWatch / Feedonomics blogs for advanced feed optimization case studies

---

## 6. Bidding Strategy Patterns

**Core pattern:** The bidding strategy is the single most impactful campaign setting. The learning is *which strategy produces optimal results under which conditions*.

**Known patterns to detect:**
- Strategy transition timing: moving from Maximize Conversions to tCPA/tROAS too early (before 50+ conversions) constrains the algorithm. Moving too late wastes budget on low-quality conversions. BrightMatter should learn the optimal transition point per vertical/budget level
- Target setting: initial targets set within 20-30% of actual historical performance work best. Over-aggressive targets cause under-delivery. Track the relationship between target aggressiveness and actual performance
- Portfolio vs. standard strategy: portfolio bidding across similar campaigns pools conversion signals, leading to faster learning. Pattern: small-volume campaigns benefit most from portfolios
- Bidding + match type interaction: broad match only works well paired with Smart Bidding. Broad match + manual CPC = budget waste. BrightMatter should flag this anti-pattern
- Marginal CPA analysis: as budget increases, CPA rises on the margin (diminishing returns). Learning the inflection point where the next dollar of spend stops being profitable per account
- Learning period protection: major changes (bidding strategy, budget >20%, conversion goal) trigger re-learning. Too-frequent changes prevent the algorithm from ever stabilizing

**Research deeper:**
- Google Ads Help: Smart Bidding overview and strategy comparison (support.google.com/google-ads/faq/10286469)
- ALM Corp: Marginal CPA analysis methodology in the 2026 audit framework
- Search Engine Land: "5 Google Ads Tactics to Drop in 2026" (searchengineland.com/google-ads-tactics-to-drop-464123) — deprecated tactics including ECPC, phrase match over-reliance

---

## 7. Campaign Structure Patterns

**Core pattern:** Structure determines what the algorithm can learn. Too granular = data fragmentation. Too consolidated = no differentiation. The learning is *what structure works for which account profile*.

**Known patterns to detect:**
- Minimum viable structure: Brand Search + Non-Brand Search + PMax (+ Shopping for ecommerce). Accounts that over-segment without sufficient conversion volume per campaign underperform
- Typical scaling structure: 6-10 campaigns with clear strategic distinctions — brand, non-brand by funnel stage, PMax by product line, remarketing, competitor, video
- Consolidation vs. segmentation: campaigns need 30-50 conversions/month minimum for Smart Bidding to optimize. Below that, consolidate. Above that, segment for control
- Device-specific campaigns: deprecated pattern in 2026. Device bid adjustments within campaigns are sufficient. Separate device campaigns fragment data
- Match-type-specific campaigns: deprecated pattern. Single ad groups with mixed match types + Smart Bidding handle this automatically
- Geographic structure: separate campaigns only when geo regions have meaningfully different economics (different CPA targets, different products, different languages)

**Research deeper:**
- LeadsBridge: "The Perfect Google Ads Campaign Structure: A Guide for 2026" (leadsbridge.com/blog/google-ads-campaign-structure/) — structure by business type, brand/non-brand separation, ad group best practices
- ALM Corp: Advanced tactics guide — campaign quantity guidelines, sweet spot recommendations
- Google: "Power Pack" recommendation (PMax + Demand Gen + AI Max for Search)

---

## 8. SEO × Paid Search Interaction Patterns

**Core pattern:** SEO and paid search are not independent channels. They interact at the keyword level, the SERP level, and the brand level. The learning is *how organic visibility changes should trigger paid strategy adjustments*.

**Known patterns to detect:**
- Organic rank decline → paid coverage increase: when a key page drops from position 1-3 to position 5+, paid impressions for those terms should increase to maintain traffic. BrightMatter should detect organic drops and recommend paid compensation
- SERP real estate doubling: brand presence in both organic and paid results lifts overall CTR for both. The combined effect is greater than either alone
- Cannibalization detection: for queries where you rank #1 organically, brand ads may be cannibalizing clicks you'd get for free. Incrementality testing reveals which terms to keep bidding on vs. which to drop
- AI Overviews impact: Google's AI Overviews push both organic and paid results down the page. Track CTR changes when AI Overviews appear for your target queries — this affects bid strategy
- Content gap → keyword opportunity: topics where you have strong organic content but no paid coverage represent expansion opportunities. Conversely, keywords where you bid heavily but have no organic presence indicate content strategy gaps
- Search Console × Google Ads overlap: comparing Search Console query data with Google Ads search term data reveals the full picture of how users find you

**Research deeper:**
- Google Search Console API for organic ranking data
- Ahrefs / SEMrush for competitive keyword gap analysis
- Studies on paid + organic SERP interaction (Brand lift studies, incrementality testing frameworks)

---

## 9. Landing Page & Conversion Rate Patterns

**Core pattern:** Landing page quality is one of three Quality Score components and the most controllable external factor. The learning is *which page characteristics produce the highest conversion rates by traffic source and intent*.

**Known patterns to detect:**
- Page speed → conversion rate: Core Web Vitals (LCP, CLS, INP) correlate with conversion rate and Quality Score. Pages loading >3 seconds lose significant conversion volume
- Message match: landing pages that mirror the exact language of the ad (headline echo, offer match) convert at 2-3x vs. generic homepages
- Mobile conversion gap: mobile conversion rates are typically 30-50% lower than desktop. Accounts that close this gap (mobile-optimized landing pages, simplified forms, tap-friendly CTAs) unlock significant budget efficiency
- Form field optimization: each additional form field reduces completion rate. For lead gen, test minimum viable form fields and track downstream lead quality
- Social proof placement: reviews, testimonials, and trust badges near CTAs lift conversion rates. The pattern differs by vertical and price point
- Post-click experience alignment: where users land after clicking should match their search intent. Product searches → product pages. Category searches → category pages. Research queries → content pages with embedded conversion paths

**Research deeper:**
- Google PageSpeed Insights API for automated Core Web Vitals monitoring
- Landingi: Quality Score and landing page optimization (landingi.com/digital-advertising/google-ads-quality-score)
- Nostra AI: Landing page experience optimization case studies (nostra.ai/blogs-collection/google-ads-landing-page-experience)
- HawkSEM: Landing page experience guide (hawksem.com/blog/landing-page-experience-google-ads/)

---

## 10. Seasonality & External Event Patterns

**Core pattern:** Performance fluctuations are often seasonal or market-driven, not account-level problems. The learning is *distinguishing between account issues and environmental changes*.

**Known patterns to detect:**
- Year-over-year seasonal curves: every vertical has a predictable annual rhythm. BrightMatter with 500 accounts across verticals should auto-detect and calibrate expectations by vertical × month
- Day-of-week patterns: B2B accounts peak Monday-Thursday, ecommerce peaks Thursday-Sunday, local services peak based on need urgency
- Platform-level shifts: when Google changes the algorithm (match type behavior, SERP layout, Smart Bidding model updates), all accounts in a vertical shift together. BrightMatter should detect "all accounts moved" vs. "one account moved"
- Macro-economic sensitivity: consumer confidence drops → conversion rates drop across ecommerce. BrightMatter should track macro indicators as context signals
- Competitive entry/exit: when a major competitor enters or exits the auction, CPC and impression share shift across the entire competitive set. Auction Insights data reveals this
- Cultural/news events: trending topics can spike or tank specific keyword categories overnight. Google Trends correlation helps distinguish viral moments from performance problems

**Research deeper:**
- Google Trends API for automated trend monitoring
- Google Ads Keyword Planner for search volume forecasting
- Industry benchmark reports: WordStream, LocaliQ, Tinuiti, Merkle quarterly performance reports
- BLS economic data for macro indicators

---

## 11. Cross-Channel Attribution Patterns

**Core pattern:** Google over-credits itself. Every channel does. The learning is *what the true cross-channel customer journey looks like and where Google Ads actually drives incremental value*.

**Known patterns to detect:**
- Assisted conversion patterns: Google Search campaigns that appear in the path-to-conversion but aren't last-click still contribute value. BrightMatter should track assisted conversions to identify campaigns that build pipeline even when they don't close it
- Channel interaction sequences: "Meta awareness → Google branded search → conversion" is a common path. Cutting Meta spend may reduce Google brand conversions — BrightMatter should detect these cross-channel dependencies
- Blended ROAS / MER reality: total revenue / total marketing spend is the ground truth metric. Individual channel ROAS is directional but not gospel. Track MER trends as the north star
- Incrementality by campaign type: brand Search often has low incrementality (organic would capture most traffic). Non-brand Search has higher incrementality. PMax incrementality varies by channel distribution within the campaign
- Attribution model impact: switching from last-click to data-driven attribution changes which campaigns appear to be performing well. BrightMatter should track the delta between attribution models to identify campaigns that are over/under-credited

**Research deeper:**
- GA4 attribution reports and cross-channel path analysis
- Northbeam / Triple Whale / Rockerbox for cross-channel measurement
- Google's geographic incrementality testing framework
- Measured (formerly Marketing Evolution) for incrementality study methodology

---

## 12. Creative & Ad Copy Patterns

**Core pattern:** In an automation-heavy world, creative is the last remaining human advantage. The learning is *which messaging frameworks produce the best performance by audience and funnel stage*.

**Known patterns to detect:**
- RSA asset performance: which headlines and descriptions get "Best" vs. "Low" ratings across accounts in the same vertical. Are there universal winning patterns?
- Headline pinning impact: pinning critical messages (brand, primary CTA) to position 1 produces more consistent messaging but may reduce Google's optimization flexibility. Pattern varies by campaign type
- Emotional vs. rational: some verticals respond to emotional hooks ("finally feel confident"), others to rational benefits ("save 40% per month"). BrightMatter should learn which approach works where
- Specificity wins: "Save $147/month" outperforms "Save money." Specific claims outperform generic claims across virtually all verticals
- Social proof in ad copy: ads that include review ratings, customer counts, or award mentions in headlines/descriptions outperform ads without these elements
- Extension/asset coverage: accounts that fill all available extensions (sitelinks, callouts, structured snippets, images) outperform accounts with minimal extensions. The marginal value of each additional extension type
- Creative refresh cadence: how frequently top-performing ad copy needs to be refreshed before CTR decline. Varies by impression volume and audience size

**Research deeper:**
- Google Ads RSA asset performance reporting
- AdSpyder / Semrush / SpyFu for competitive ad copy analysis
- Google's Ad Strength diagnostic as a creative quality signal
- A/B testing frameworks for systematic creative optimization

---

## Summary: Research Priority for BrightMatter

**Highest priority (study first — these are the core decision patterns):**
1. Branded vs. non-branded separation and measurement
2. Bidding strategy selection and transition timing
3. PMax input optimization (feed, assets, audience signals, conversion goals)
4. Quality Score component optimization (especially landing page experience)
5. Campaign structure by account profile (spend level, vertical, conversion volume)

**Second priority (study once ingestion is running):**
6. Match type strategy and keyword lifecycle management
7. Cross-channel attribution and incrementality
8. Seasonality normalization and anomaly detection
9. Creative/ad copy testing frameworks
10. Shopping feed optimization

**Third priority (study once patterns are forming):**
11. YouTube creative patterns and funnel stage alignment
12. SEO × paid interaction patterns
13. Competitive intelligence and auction dynamics
14. External event detection and macro sensitivity

Each of these areas becomes a **domain** in BrightMatter's learning system — a distinct pattern vocabulary where the system accumulates episodes, consolidates them into semantic patterns, and uses those patterns to generate increasingly accurate guidance.
