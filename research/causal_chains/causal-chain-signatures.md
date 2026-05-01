# BrightMatter: Causal Chain Detection Signatures

> External cause → Google Ads effect chains for pattern recognition across 500 accounts.
> Research compiled April 2026.

---

## Chain 1: Tracking & Measurement Breaks

### Detection Signature
- Conversions drop >80% across ALL campaigns on the same day
- Clicks and impressions remain stable (traffic still flowing)
- CPA spikes to infinity (cost / 0 conversions)
- All conversion actions show zero simultaneously (not just one action)
- Conversion rate drops to near-zero while CTR unchanged
- Pattern: `conversions_t / conversions_t-1 < 0.2` AND `clicks_t / clicks_t-1 > 0.8` across all campaigns

### Diagnostic Test
1. Check if conversion drop affects ALL campaigns or just some — tracking breaks affect everything
2. Verify clicks are stable — if clicks also dropped, it's a different problem (paused campaigns, budget exhaustion)
3. Check Google Tag status in Google Ads > Tools > Conversions — look for "No recent conversions" or "Inactive" tag status
4. Compare conversion counts by conversion action — if ALL actions dropped, it's a global tag issue; if only one dropped, it may be a single action misconfiguration
5. Check Google Tag Assistant / GTM debug mode for the landing pages
6. Look at Change History for conversion action modifications (added/removed/edited)
7. Cross-reference with website deployment logs — site updates that break GTM containers or remove conversion snippets

### Time Constants
- Cause-to-effect delay: 0–4 hours (nearly immediate; depends on conversion tracking method)
- Recovery time after fix: 1–24 hours for tag-based tracking; 24–72 hours for imported conversions (GA4 → Google Ads) due to processing lag

### Cross-Account Signal
- **Single account**: If only one account affected, it's that account's website/tag
- **Multiple accounts on same domain/property**: If a shared GTM container breaks, multiple accounts tracking the same site are affected simultaneously
- BrightMatter should flag when conversion drops correlate with specific domains, not advertiser-level patterns

### Known Automated Detection Methods
- **Google Ads Scripts — Account Anomaly Detector**: Compares current stats against 26-week historical baseline for same day-of-week; runs hourly, sends one alert/day. Available at: developers.google.com/google-ads/scripts/docs/solutions/account-anomaly-detector
- **Adcrease Conversion Action Alert Script**: Monitors specific conversion actions; sends email alerts when no conversions recorded within N days. Tracks last conversion date per action.
- **Granular Conversion Drop Script**: Compares conversions across 1/3/7-day windows; triggers alerts if conversions drop by configurable threshold (default 95%). Catches tracking issues before significant budget waste.
- **Google Tag Assistant**: Browser extension for manual verification of tag firing
- **Google Ads UI**: Tools > Conversions shows tag status ("Recording", "Inactive", "No recent conversions")

### Sources
- https://developers.google.com/google-ads/scripts/docs/solutions/account-anomaly-detector
- https://adcrease.nl/article/google-ads-script-conversion-action-alert/
- https://granularmarketing.com/blog/proactive-conversion-tracking-the-script-every-google-ads-account-needs/
- https://adsanomalyguard.com/blog/google-ads-conversion-tracking-broken
- https://support.google.com/tagassistant/answer/2947038

---

## Chain 2: Website & Landing Page Changes

### Detection Signature
- CVR drops isolated to specific landing page URLs while overall traffic volume and CTR remain stable
- Quality Score "Landing page experience" component degrades from "Above average" or "Average" to "Below average"
- Bounce rate increases on affected URLs (visible in GA4 linked data)
- Average page load time increases (correlated with CWV degradation)
- Pattern: `CVR_url_t / CVR_url_t-7 < 0.7` AND `CTR_t ≈ CTR_t-7` AND `clicks_t ≈ clicks_t-7`
- If site-wide redesign: ALL landing pages show CVR drop simultaneously

### Diagnostic Test
1. Isolate CVR changes by landing page URL — is the drop on specific URLs or site-wide?
2. Check Core Web Vitals for affected URLs (PageSpeed Insights, CrUX data) — LCP >2.5s, INP >200ms, CLS >0.1 are red flags
3. Compare QS landing page component before/after the change date — note QS updates lag 2–4 weeks behind actual page changes
4. Check CMS/deployment logs for site updates matching the performance shift date
5. Test the landing page manually — is it functional? Does the form work? Is the CTA visible?
6. Look for redirect chains introduced during migration (HTTP → HTTPS, www → non-www)
7. Check if mobile vs. desktop CVR diverged (mobile more sensitive to page speed)

### Time Constants
- Cause-to-effect delay: 0–24 hours for CVR impact (immediate user experience); 2–4 weeks for QS landing page component to update
- Recovery time after fix: CVR recovers within 1–3 days after fix; QS landing page component takes 2–4 weeks to re-evaluate

### Cross-Account Signal
- **Single account**: Typically affects only the account whose website changed
- **Multiple accounts**: If accounts share a landing page domain (e.g., agency-managed clients on shared infrastructure), a hosting issue could affect multiple accounts
- **Not an industry pattern**: Unlike CPC inflation, this is account/site-specific

### Known Automated Detection Methods
- **Google Ads Scripts**: Custom scripts comparing CVR by final URL over rolling windows
- **Google PageSpeed Insights API**: Automated CWV monitoring; can be scheduled to check landing pages daily
- **CrUX API (Chrome User Experience Report)**: Provides field data for Core Web Vitals at origin and URL level
- **Google Ads QS monitoring scripts**: Track historical_landing_page_quality_score via API, alert on downgrades

### Sources
- https://www.digitalagencynet.com/page-speed-impact-google-ads.html
- https://roamdigital.co.uk/how-page-speed-affects-google-ads-quality-score/
- https://vjseomarketing.com/blog/core-web-vitals-optimization-guide
- https://ppcinfo.com/en/articles/core-web-vitals-seo-rankings-2026

---

## Chain 3: Industry-Wide CPC Inflation

### Detection Signature
- CPC rises across ALL keywords in an account — not isolated to specific ad groups or campaigns
- Impression Share (IS) drops if budgets remain flat (same budget buys fewer clicks at higher CPCs)
- The same CPC increase pattern appears across MULTIPLE accounts in the same vertical simultaneously
- Search impression share lost to budget increases; search impression share lost to rank stays stable
- Pattern: `avg_cpc_t / avg_cpc_t-30 > 1.15` across all accounts in vertical AND `IS_budget_lost` increases

### Diagnostic Test
1. Compare CPC trends across ALL accounts in the same vertical — if 80%+ show the same increase, it's industry-wide
2. Check Tinuiti/WordStream quarterly benchmark reports for the vertical's CPC trend
3. Look at Auction Insights — if new competitors appeared (higher overlap rates) AND CPCs rose, it's competitive pressure, not pure inflation
4. Compare against accounts in DIFFERENT verticals — if they're also up, it may be platform-wide
5. Check if the increase correlates with seasonal peaks (Q4 holiday, back-to-school, tax season)
6. Examine IS lost to rank vs. IS lost to budget — pure CPC inflation shows up as IS lost to budget with flat budgets

### Time Constants
- Cause-to-effect delay: Gradual over weeks/months (macro inflation) or sudden over days (seasonal peak / major competitor entry)
- Recovery time after fix: No "fix" — this is environmental. Budget increases or efficiency gains needed. Seasonal inflation subsides after the peak period (1–4 weeks)

### Cross-Account Signal
- **Strong multi-account signal**: This is THE defining characteristic — affects many/all accounts in a vertical
- BrightMatter's 500-account view is uniquely positioned to detect this: compute median CPC change by vertical, flag when >70% of accounts in a vertical show >10% CPC increase in the same period
- Distinguish from account-level bid changes by checking change history for bid modifications

### Known Automated Detection Methods
- **Tinuiti Digital Ads Benchmark Reports** (quarterly): Track CPC trends across $4B+ in managed spend; available at tinuiti.com/research-insights
- **WordStream Industry Benchmarks** (annual): CPC by industry with YoY comparison; reports CPC increased for 87% of industries in 2025
- **Google Ads Scripts**: Cross-account CPC comparison scripts at MCC level
- **BrightMatter-specific**: Cross-account CPC percentile tracking with vertical segmentation

### Sources
- https://tinuiti.com/research-insights/research/digital-ads-benchmark-report-q3-2025/
- https://wordstream.com/blog/2025-google-ads-benchmarks
- https://www.rockingweb.com.au/google-ads-benchmarks-by-industry-2025

---

## Chain 4: Competitor Entry/Exit/Strategy Change

### Detection Signature
- Auction Insights metrics shift: new domain appears with high overlap rate (>30%), or existing competitor's impression share jumps significantly
- CPC increases on specific keyword clusters (not account-wide like CPC inflation)
- Impression Share drops on affected keyword clusters while remaining stable elsewhere
- Outranking share decreases for specific competitors
- Pattern: `auction_insight_overlap_rate_competitor_X` increases >15pp AND `avg_cpc_keyword_cluster` increases >20%
- Competitor exit: opposite pattern — IS increases, CPCs decrease, outranking share improves

### Diagnostic Test
1. Pull Auction Insights report segmented by time period — identify when the shift began
2. Check if CPC changes are localized to specific keyword themes or across the board
3. Look for new domains in Auction Insights that weren't present in prior periods
4. Check if existing competitors' impression share changed dramatically (>10pp shift)
5. Use outranking share + position above rate to determine if the competitor is bidding aggressively or just present
6. Cross-reference with SEMrush/SpyFu/SimilarWeb for competitor ad spend intelligence
7. Check if the pattern affects multiple accounts in the same vertical (competitor is broad) or just one account (competitor is niche)

### Time Constants
- Cause-to-effect delay: 1–7 days (competitors launching campaigns take 1–3 days to ramp; budget changes are immediate)
- Recovery time after fix: Not directly fixable — competitive response needed. Effects persist until competitive equilibrium reached (2–8 weeks)

### Cross-Account Signal
- **Depends on competitor scope**: A national competitor entering affects all accounts in the vertical; a local competitor affects only accounts in the same geo
- BrightMatter should correlate Auction Insights domain overlap changes across accounts in the same vertical and geo
- Important: as of April 2025, Google allows double-serving (multiple ads from same advertiser on same SERP), which changes interpretation

### Known Automated Detection Methods
- **Google Ads Auction Insights** (UI only — not directly available via API for all metrics, but `auction_insight_domain` segment available on `keyword_view`)
- **Auction Insights metrics via API**: `auction_insight_search_impression_share`, `auction_insight_search_overlap_rate`, `auction_insight_search_outranking_share`, `auction_insight_search_position_above_rate`, `auction_insight_search_absolute_top_impression_percentage`, `auction_insight_search_top_impression_percentage`
- **SEMrush/SpyFu**: Third-party competitive intelligence tools
- **Custom scripts**: MCC-level scripts comparing auction insights data across accounts in same vertical

### Sources
- https://support.google.com/google-ads/answer/2579754
- https://www.karooya.com/blog/google-ads-auction-insights-2026-guide-to-tracking-and-outmaneuvering-your-competitors/
- https://benly.ai/learn/google-ads/google-ads-auction-insights

---

## Chain 5: Google Platform & Algorithm Changes

### Detection Signature
- Performance shift (CPC, CTR, conversion rate, impression volume) across MULTIPLE accounts simultaneously with NO logged changes in any account
- Change History shows no human or auto-applied modifications in affected accounts
- Shift often correlated with Google's public announcements or Search Engine Land/PPC community reports
- Smart Bidding behavior changes: bid patterns shift without target changes
- Pattern: `performance_metric_change > 2_sigma` across >30% of all accounts AND `change_event_count = 0` in affected accounts during the shift period

### Diagnostic Test
1. Check change history for ALL affected accounts — confirm zero changes logged in the shift period
2. Determine if the shift is cross-vertical (platform-wide) or vertical-specific
3. Check Google Ads product announcements, Search Engine Land, PPC subreddit for platform change reports
4. Look at the type of metric affected — SERP layout changes affect CTR/position; algorithm changes affect Smart Bidding behavior; match type changes affect search term relevance
5. Compare Smart Bidding accounts vs. manual bidding accounts — if only automated accounts are affected, it's likely a Smart Bidding update
6. Check if the shift reverses after 1–2 weeks (Google rollback) or persists (new normal)

### Time Constants
- Cause-to-effect delay: 0–48 hours (most platform changes take effect immediately or within a few days)
- Recovery time after fix: No "fix" — adaptation required. Smart Bidding re-learning takes 1–2 conversion cycles (typically 1–4 weeks). Some changes are permanent (e.g., broad match expansion, SERP layout changes)

### Cross-Account Signal
- **Strong multi-account signal**: THE hallmark — affects many accounts simultaneously across verticals
- BrightMatter is uniquely positioned: flag when >40% of accounts show a significant metric shift in the same 48-hour window with no change history entries
- Build a platform change timeline and cross-reference against detected shifts

### Known Automated Detection Methods
- **BrightMatter cross-account anomaly detection**: Flag simultaneous shifts across accounts
- **Search Engine Land / Google Ads changelog monitoring**: Manual tracking of announced changes
- **Google Ads API Recommendations resource**: New recommendations appearing across accounts may signal platform changes

### Key Platform Changes Timeline (2024–2026)
| Date | Change | Expected Effect |
|------|--------|----------------|
| June 2024 | AI-powered broad match improvements | 10% performance uplift for Smart Bidding + broad match |
| July 2024 | Broad match becomes default for new Search campaigns | More broad match traffic, potential relevance issues |
| April 2025 | Double-serving policy allows multiple ads per advertiser on same SERP | Auction Insights interpretation changes |
| September 2026 (planned) | DSA, ACA, campaign-level broad match auto-upgrade to AI Max | Forced automation migration, potential performance disruption |

### Sources
- https://support.google.com/google-ads/answer/15070437
- https://blog.google/products/ads-commerce/dsa-upgrade-to-ai-max-2026/
- https://benly.ai/learn/google-ads/google-ads-broad-match-2026
- https://searchengineland.com

---

## Chain 6: Seasonality & Calendar Events

### Detection Signature
- Traffic volume (impressions, clicks) and CVR follow calendar patterns that repeat year-over-year
- CPC spikes during peak seasons (Q4 holiday for retail, January for fitness/finance, spring for home services)
- Pattern matches prior year: `metric_t / metric_t-365 ≈ 1.0 ± 0.15` (adjusting for growth trends)
- Not correlated with any account changes — purely calendar-driven
- Budget exhaustion accelerates during demand peaks
- Pattern: `impressions_week / impressions_week-52 > 1.3` AND no campaign changes AND known seasonal period

### Diagnostic Test
1. Compare current period performance against same period last year (YoY)
2. Check Google Trends for the vertical's core keywords — seasonal patterns visible
3. Verify no campaign changes were made that coincide with the seasonal shift
4. Check if the pattern is consistent with known seasonal peaks for the vertical:
   - **Retail/E-commerce**: Q4 surge (Oct–Dec), Black Friday spike
   - **Tax/Finance**: January–April peak
   - **Home Services**: Spring peak (Mar–May)
   - **Education**: July–September enrollment period
   - **Travel**: Summer + holiday booking windows
5. Use Google Ads seasonality adjustments API (`bidding_seasonality_adjustment`) for known events

### Time Constants
- Cause-to-effect delay: 0 days (seasonality IS the timeframe)
- Recovery time after fix: Not applicable — seasonal patterns are expected. Smart Bidding's seasonality adjustments should be set 1–2 weeks before expected events for events up to 14 days long. For longer seasonal cycles, budget reallocation is the strategy.

### Cross-Account Signal
- **Strong vertical-specific signal**: All accounts in the same vertical show the same seasonal pattern
- Cross-vertical seasons (e.g., Q4 holiday) affect most verticals but to different degrees
- BrightMatter should build vertical-specific seasonal baselines from historical data across all accounts

### Known Automated Detection Methods
- **Google Ads Bidding Seasonality Adjustments**: API resource `bidding_seasonality_adjustment` allows CVR modifiers (0.1–10.0x) for periods up to 14 days, targeting specific channels/campaigns/devices
- **Google Ads Scripts**: YoY comparison scripts using `LAST_YEAR` date ranges
- **Tinuiti/WordStream Benchmark Reports**: Quarterly data provides seasonal context by vertical
- **Black Friday CPC data**: Costs spike ~26%, conversions surge ~33% (2025 benchmark)

### Sources
- https://developers.google.com/google-ads/api/fields/v22/bidding_seasonality_adjustment
- https://growthiqdigital.com/blog/google-ads-seasonality-adjustments/
- https://www.icrossing.com/insights/google-ads-seasonality-six-step-guide
- https://www.rockingweb.com.au/google-ads-benchmarks-by-industry-2025

---

## Chain 7: Privacy & Tracking Infrastructure Changes

### Detection Signature
- Reported conversions decline while actual business outcomes (revenue in CRM, leads in CRM, orders in backend) remain stable or grow
- The gap between Google Ads reported conversions and CRM/backend conversions widens over time
- iOS traffic conversion rate drops disproportionately vs. Android/desktop
- Modeled conversions percentage increases (visible in conversion action settings)
- Pattern: `google_ads_conversions / crm_conversions < 0.7` AND `crm_conversions_t ≈ crm_conversions_t-30`
- Safari/iOS segments show larger conversion declines than Chrome/Android

### Diagnostic Test
1. Compare Google Ads reported conversions against CRM/backend data for the same period
2. Segment conversion data by device/browser — if iOS/Safari shows steeper decline, it's privacy-related
3. Check Consent Mode implementation status — verify consent_mode_was_used field in conversion data
4. Look at modeled vs. observed conversion split (available in Google Ads UI under Conversions > Columns)
5. Check if the decline is gradual (ongoing privacy erosion) vs. sudden (a specific privacy update like iOS version release)
6. Verify Enhanced Conversions implementation status
7. Compare EEA/UK traffic conversion rates vs. non-EEA (Consent Mode v2 impact)

### Time Constants
- Cause-to-effect delay: Gradual — iOS ATT impact was immediate per iOS version rollout; Consent Mode v2 mandatory since March 2024; cookie deprecation is ongoing
- Recovery time after fix: Implementing Enhanced Conversions recovers 5–15% of lost conversions within 1–2 weeks; Consent Mode recovery depends on consent rates (typically 30–60% of EU users consent)

### Cross-Account Signal
- **Universal signal**: Affects ALL accounts, but degree varies by audience composition (B2C with high iOS users = more affected; B2B with desktop Chrome users = less affected)
- The measurement gap grows over time for all accounts — BrightMatter should track the ratio of reported:actual conversions per account
- EEA-targeted accounts are more affected than US-only accounts due to Consent Mode v2

### Known Automated Detection Methods
- **Google Ads Conversion Diagnostics**: Shows conversion action health, modeled conversion percentage
- **Enhanced Conversions monitoring**: API fields for enhanced conversion upload status
- **CRM comparison scripts**: Automated reconciliation between Google Ads and CRM conversion counts
- **Consent Mode diagnostics**: Google Tag Manager Consent Mode debugging tools
- **WBRAID parameter tracking**: Monitor iOS conversion attribution via new URL parameters

### Sources
- https://support.google.com/google-ads/answer/10417364
- https://support.google.com/google-ads/answer/10635155
- https://support.google.com/google-ads/answer/10384955
- https://www.flowconsent.com/en/blog/google-consent-mode-v2-guide

---

## Chain 8: Search Demand Shifts

### Detection Signature
- Impression volume changes significantly with NO campaign setting changes (no bid changes, no keyword additions, no budget changes)
- Google Trends data for core keywords shows matching volume shifts
- Clicks and impressions move together (CTR stays relatively stable)
- Can be sudden (viral event, news) or gradual (AI chat search cannibalizing traditional search)
- Pattern: `impressions_t / impressions_t-30 < 0.7 OR > 1.5` AND `change_event_count = 0` AND `google_trends_volume_change matches`
- AI Overviews impact: queries with AI Overviews show ~58% lower CTR vs. queries without (2026 data)

### Diagnostic Test
1. Check Google Trends for the account's core keywords — does the impression change match search volume change?
2. Verify no campaign changes occurred (change history clean)
3. Determine if the shift is query-specific or category-wide
4. Check if AI Overviews are appearing for the account's target queries (queries with AI Overviews show ~2.1% CTR vs. ~3.3% without)
5. Look for cultural/news events that may have driven sudden interest shifts
6. Check impression share — if IS is stable but impressions dropped, the total market shrank; if IS dropped, it's competitive
7. Compare branded vs. non-branded — branded demand shifts indicate awareness changes; non-branded indicates category demand changes

### Time Constants
- Cause-to-effect delay: 0–7 days for sudden events (news, viral content); months/years for structural shifts (AI search cannibalization)
- Recovery time after fix: Demand shifts are not "fixable" — they require strategic response (new keywords, audience expansion, channel diversification)

### Cross-Account Signal
- **Vertical-specific**: Demand shifts typically affect all accounts targeting the same keyword themes
- BrightMatter should track impression volume trends by keyword cluster across accounts to detect demand contraction vs. account-level issues
- AI Overviews impact varies by vertical: Technology and comparison queries most affected (95% show AI Overviews); transactional queries least affected (~5%)

### Known Automated Detection Methods
- **Google Trends API**: Automated monitoring of search interest for target keywords
- **Google Ads impression volume tracking scripts**: Alert on significant impression changes without campaign modifications
- **AI Overview monitoring tools**: Track which queries trigger AI Overviews (Adthena, Seer Interactive)
- **Search Console data**: Organic impression data can corroborate search demand changes

### Sources
- https://searchengineland.com/what-industry-data-reveals-about-the-impact-of-googles-ai-overviews-on-paid-search-470019
- https://www.adthena.com/resources/blog/aios-on-paid-search/
- https://adsroid.com/impact-ai-overviews-google-click-through-rates-2026/
- https://www.seerinteractive.com/insights/aio-impact-on-google-ctr-2026-update

---

## Chain 9: Product/Pricing/Inventory Changes

### Detection Signature
- CVR changes correlated with price changes in the product feed
- Shopping/PMax product groups losing impressions when products go out of stock
- Specific product-level performance changes while campaign settings unchanged
- ROAS changes driven by AOV shifts (price increases → fewer conversions but higher value, or vice versa)
- Pattern: `CVR_product_group_t / CVR_product_group_t-7 < 0.7` AND `price_feed_change_detected`
- Price sensitivity varies: Electronics CVR elasticity = -1.72; Fashion = -0.89

### Diagnostic Test
1. Check Merchant Center feed for price changes, stock status changes, or disapprovals
2. Correlate CVR changes with product-level price changes — higher prices → lower CVR (with category-specific elasticity)
3. Check Shopping product report for products with `item_status = OUT_OF_STOCK`
4. Look at product group performance by listing group filter dimensions
5. Compare competitor pricing using Merchant Center price competitiveness report
6. Check if the change is product-specific or category-wide
7. Look at cart data metrics (available in Shopping/PMax): `average_cart_size`, `average_order_value_micros`, `cost_of_goods_sold_micros`

### Time Constants
- Cause-to-effect delay: 0–24 hours (price/inventory changes reflected in feed within hours; CVR impact is immediate once the feed updates)
- Recovery time after fix: 1–3 days for restocking; CVR recovery from price changes is immediate once price adjusted; Smart Bidding readjustment takes 1–2 weeks after feed changes stabilize

### Cross-Account Signal
- **Single account**: Product/pricing changes are account-specific
- **Exception**: Industry-wide price inflation (e.g., tariff impacts) could affect all accounts in a product category
- **Marketplace accounts**: Multiple sellers on same platform may see simultaneous feed issues

### Known Automated Detection Methods
- **Merchant Center feed diagnostics**: Automated alerts for disapprovals, price changes, stock issues
- **Google Ads Shopping Product resource** (`shopping_product`): Query for item status, price, availability
- **Custom scripts**: Compare product feed prices against historical baselines; alert on >10% price changes
- **Cart data reporting**: Available via API for Shopping and PMax campaigns

### Sources
- https://smarter-ecommerce.com/blog/en/data-science/how-pricing-influences-conversion-rates-a-case-study/
- https://www.42signals.com/blog/price-elasticity-ecommerce/
- https://americanimpactreview.com/article/e2026015
- https://developers.google.com/google-ads/api/performance-max/retail-reporting

---

## Chain 10: Cross-Channel Spillover

### Detection Signature
- Brand search volume changes (impressions for brand keywords) without any Google Ads changes
- Changes correlated with Meta/social/TV/PR spend changes on other platforms
- Pattern: `brand_impressions_t / brand_impressions_t-30 < 0.8` AND `no_google_ads_changes` AND `meta_spend_decreased`
- When Meta prospecting spend is cut, Google branded search volume declines (documented but magnitude varies)
- New brand campaigns or PR events → brand search volume spike in Google Ads

### Diagnostic Test
1. Check brand keyword impression trends — is branded search volume changing?
2. Correlate with Meta/social ad spend timeline — was spend increased or decreased on other platforms?
3. Look for PR events, TV airings, or viral social content that could drive brand awareness
4. Check Google Trends for brand name — matches awareness-driven search patterns
5. Compare brand vs. non-brand search performance — if only brand is affected, it's an awareness/demand issue, not a Google Ads issue
6. Use Marketing Mix Modeling (MMM) tools (Google Meridian, Meta Robyn) for attribution
7. Check email campaign calendar — large email sends can temporarily boost branded search

### Time Constants
- Cause-to-effect delay: 1–14 days (Meta spend cuts take 1–2 weeks to show up in brand search; PR/TV effects are faster, 1–3 days)
- Recovery time after fix: 1–2 weeks after restoring upper-funnel spend; PR-driven spikes decay over 3–7 days

### Cross-Account Signal
- **Single account** (typically): Cross-channel effects are specific to each brand/advertiser
- **Exception**: If a platform-wide change occurs (e.g., Meta outage, TikTok ban), multiple accounts' brand search volumes could be affected simultaneously
- BrightMatter should track brand search volume trends and correlate with known cross-channel spend data where available

### Known Automated Detection Methods
- **Google Ads brand keyword impression tracking**: Monitor brand term impressions separately
- **Google Trends API**: Track brand interest over time
- **MMM platforms**: Google Meridian, Meta Robyn, Prescient AI — quantify cross-channel lift
- **Incrementality testing**: Geo-based lift studies for cross-channel effect measurement
- **Custom CRM correlation**: Compare CRM lead source data against Google Ads brand metrics

### Sources
- https://prescientai.com/blog/brand-incrementality
- https://cresva.ai/guides/budget-allocation
- https://www.darkroomagency.com/observatory/google-ads-vs-meta-ads-ecommerce-budget-2026
- https://www.silverbackstrategies.com/blog/the-causal-pivot-why-google-and-meta-are-giving-you-the-tools-to-grade-their-homework/

---

## Chain 11: Auto-Applied Recommendations

### Detection Signature
- Performance shifts with no logged HUMAN change in change history
- Change history entries show `client_type` = `GOOGLE_ADS_RECOMMENDATIONS` or `GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION`
- User email field empty or shows "Google Ads" as the actor
- Changes often affect keywords (broad match additions), bidding strategy, ad rotation, or audiences
- Pattern: `change_event.client_type IN (GOOGLE_ADS_RECOMMENDATIONS, GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION)` correlated with performance shift

### Diagnostic Test
1. Query Change History API for `change_event` with `client_type = GOOGLE_ADS_RECOMMENDATIONS` or `GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION` in the shift period
2. Identify what was changed: keyword match type? bid strategy? targeting? ad copy?
3. Check auto-apply settings in Account Settings > Recommendations > Auto-apply
4. Assess which recommendation types were auto-applied:
   - **Lower risk**: Optimized ad rotation, adjust CPA/ROAS targets (fine-tuning)
   - **Higher risk**: Add broad match keywords, switch bid strategies, add audience segments, AI Max upgrade
5. Compare performance before/after the auto-applied change date
6. Check if the same auto-applied recommendation affected multiple accounts (common for accounts in the same MCC with shared auto-apply settings)

### Time Constants
- Cause-to-effect delay: 0–72 hours (changes take effect immediately; performance impact may take 1–3 days to materialize, especially bid strategy changes)
- Recovery time after fix: Reverting the change: 1–3 days for bid strategy re-stabilization; immediate for keyword/targeting reversions; Smart Bidding re-learning after revert: 1–2 conversion cycles (1–4 weeks)

### Cross-Account Signal
- **MCC-level pattern**: If auto-apply is enabled at MCC level, multiple accounts may receive the same recommendation simultaneously
- BrightMatter should detect when multiple accounts in the same MCC show performance shifts correlated with auto-applied changes
- Individual accounts can also have auto-apply enabled independently

### Known Automated Detection Methods
- **Google Ads API Change Event**: `change_event` resource with `client_type` filtering — distinguishes human from auto-applied changes. Key enum values: `GOOGLE_ADS_AUTOMATED_RULE`, `GOOGLE_ADS_RECOMMENDATIONS`, `GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION`
- **Google Ads UI**: Account Settings > Auto-apply shows which recommendations are enabled
- **Google Ads Results Tab** (launched Feb 2026): Shows performance impact of applied recommendations with 1-week before/after comparison
- **Custom API scripts**: Query `change_event` filtered by client_type for non-human changes

### Sources
- https://support.google.com/google-ads/answer/10279006
- https://ppcpanos.com/how-to-fix-aar-in-google-ads/
- https://searchengineland.com/google-ads-adds-results-tab-to-show-impact-of-applied-recommendations-469390
- https://developers.google.com/google-ads/api/docs/change-event
- https://github.com/googleapis/googleapis/blob/master/google/ads/googleads/v23/enums/change_client_type.proto

---

## Chain 12: Conversion Definition & Attribution Changes

### Detection Signature
- Reported conversions change (up or down) without actual business outcome changes
- Conversion action change log shows additions, removals, or primary/secondary reclassification
- Attribution model change: credit shifts across campaigns (some gain conversions, others lose)
- Smart Bidding enters learning period after conversion definition change
- Pattern: `conversions_t / conversions_t-1 changes >20%` AND `conversion_action_settings_changed` AND `actual_business_outcomes_stable`
- Time lag in reporting increases after switching to non-last-click attribution models

### Diagnostic Test
1. Check conversion action settings for changes: new actions added, existing removed, primary ↔ secondary reclassification
2. Look at Change History for conversion-related modifications
3. Compare `conversions` vs. `all_conversions` metrics — if `conversions` changed but `all_conversions` stable, it's a primary/secondary reclassification
4. Check attribution model changes on conversion actions — switching from last-click to data-driven affects conversion counts and timing
5. Verify with CRM/backend data that actual outcomes haven't changed
6. Look for conversion action deduplication changes (counting "one" vs. "every" conversion)
7. Check conversion window changes (30-day → 7-day window reduces reported conversions)

### Time Constants
- Cause-to-effect delay: 0–24 hours for conversion definition changes to take effect; attribution model changes may take several days to show in reporting due to conversion lag
- Recovery time after fix: Smart Bidding re-learning after conversion definition change: 1–2 conversion cycles (~50 conversion events or 2–4 weeks). Attribution model stabilization: 2–4 weeks as historical conversion lag catches up

### Cross-Account Signal
- **Single account**: Conversion definition changes are account-specific
- **Exception**: MCC-level conversion goals or cross-account conversion tracking changes can affect multiple accounts
- If multiple accounts suddenly show conversion volume shifts with no campaign changes, check for shared conversion infrastructure changes

### Known Automated Detection Methods
- **Google Ads API**: Query `conversion_action` resource for `status`, `type`, `category`, `attribution_model_settings`, `counting_type`, `click_through_lookback_window_days`, `view_through_lookback_window_days`
- **Change Event API**: Filter for `change_resource_type = CONVERSION_ACTION` to detect conversion action modifications
- **Google Ads UI**: Tools > Conversions shows change history for each conversion action
- **Custom monitoring scripts**: Track conversion action configuration hashes daily; alert on any changes
- **Smart Bidding learning period indicator**: Available in campaign status column

### Sources
- https://support.google.com/google-ads/answer/14571185
- https://support.google.com/google-ads/answer/9203352
- https://support.google.com/google-ads/answer/6268633
- https://support.google.com/google-ads/answer/13020501

---

## Summary: Detection Priority Matrix

| Chain | Detection Confidence | Cross-Account Value | API Data Available | BrightMatter Priority |
|-------|---------------------|--------------------|--------------------|----------------------|
| 1. Tracking Breaks | Very High | Medium | High | P0 — Critical |
| 2. Landing Page Changes | High | Low | Medium (QS only) | P1 |
| 3. CPC Inflation | High | Very High | High | P0 — Core value prop |
| 4. Competitor Changes | Medium | High | High (Auction Insights) | P0 — Core value prop |
| 5. Platform Changes | Medium | Very High | Low (no direct signal) | P0 — Core value prop |
| 6. Seasonality | High | High | High | P1 |
| 7. Privacy/Tracking | Medium | High | Medium | P1 |
| 8. Search Demand Shifts | Medium | High | Medium | P1 |
| 9. Product/Pricing | High | Low | High (Shopping) | P2 |
| 10. Cross-Channel | Low | Low | Low | P2 |
| 11. Auto-Applied | Very High | Medium | Very High | P0 — Easy win |
| 12. Conv. Definition | Very High | Low | Very High | P1 |
