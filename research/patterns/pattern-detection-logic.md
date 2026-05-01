# BrightMatter Pattern Detection Logic
## Google Ads Pattern Recognition Engine — 500 Accounts, Cross-Vertical

> Generated: 2026-04-29
> Purpose: Quantified thresholds and detection pseudocode for implementation

---

## Domain 1: Branded Search Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Brand CPC increase WoW | >15% for 2+ consecutive weeks | Flag as competitor-driven if Auction Insights overlap rises simultaneously |
| Auction Insights overlap rate (brand terms) | >30% impression share from competitors | Trigger brand defense alert |
| Brand vs non-brand ROAS contamination | Brand ROAS >10x while non-brand ROAS <2x in blended reporting | Flag as "inflated blended ROAS" |
| PMax brand leakage | PMax conversion efficiency jumps >20% without matching total account conversion lift | Flag brand demand flowing to PMax |
| Brand CPC (baseline) | $0.50–$2.00 typical | CPC exceeding 2x baseline = competitor pressure |
| Non-brand CPC (baseline) | $2.00–$10.00 typical | — |
| Brand conversion rate | 15–30% | Drop below 10% = landing page or SERP issue |
| Non-brand conversion rate | 2–5% | — |

**Competitor-driven vs. organic CPC increase:**
- If brand CPC rises >15% AND Auction Insights shows new competitor or competitor impression share increase >5pp → competitor-driven
- If brand CPC rises >15% AND Auction Insights is stable AND organic rank unchanged → likely platform-level CPC inflation
- If brand CPC rises AND organic position drops (e.g., AI Overviews displacing organic) → SERP-structure-driven

### Minimum Data Requirements

- 30 days of brand campaign data minimum
- Auction Insights segmented by brand keywords specifically
- Organic rank data from Search Console for brand terms
- At least 100 brand conversions/month for reliable ROAS comparison
- 5+ accounts in same vertical for benchmark validity

### Detection Logic (Pseudocode)

```python
def detect_brand_cpc_creep(account, lookback_weeks=4):
    brand_cpc_series = get_weekly_brand_cpc(account, weeks=lookback_weeks)
    auction_insights = get_auction_insights(account, campaign_type='brand')

    cpc_increase_pct = (brand_cpc_series[-1] - brand_cpc_series[-3]) / brand_cpc_series[-3]
    competitor_overlap_change = auction_insights.current_overlap - auction_insights.prior_overlap

    if cpc_increase_pct > 0.15 and competitor_overlap_change > 0.05:
        return Alert("COMPETITOR_DRIVEN_CPC_CREEP", severity="high",
                     details=f"Brand CPC up {cpc_increase_pct:.0%}, "
                             f"competitor overlap up {competitor_overlap_change:.0%}")

    if cpc_increase_pct > 0.15 and competitor_overlap_change <= 0.05:
        return Alert("PLATFORM_CPC_INFLATION", severity="medium")

    return None


def detect_brand_nonbrand_contamination(account):
    brand = get_campaign_metrics(account, label='brand')
    nonbrand = get_campaign_metrics(account, label='nonbrand')
    blended = get_account_metrics(account)

    if brand.roas > 10 and nonbrand.roas < 2 and blended.roas > 5:
        return Alert("ROAS_CONTAMINATION",
                     details=f"Blended ROAS {blended.roas:.1f}x masks "
                             f"non-brand ROAS of {nonbrand.roas:.1f}x")

    return None


def detect_pmax_brand_leakage(account):
    pmax = get_campaign_metrics(account, type='PERFORMANCE_MAX')
    total = get_account_metrics(account)
    brand_search = get_campaign_metrics(account, label='brand')

    pmax_conv_lift = pmax.conversions_delta_pct(weeks=4)
    total_conv_lift = total.conversions_delta_pct(weeks=4)
    brand_conv_change = brand_search.conversions_delta_pct(weeks=4)

    if pmax_conv_lift > 0.20 and total_conv_lift < 0.05 and brand_conv_change < -0.10:
        return Alert("PMAX_BRAND_LEAKAGE", severity="high",
                     details="PMax absorbing brand demand without incremental growth")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Brand Shopping listings capture brand intent early; Shopping gravity makes PMax leakage more severe. Monitor Shopping impression share on brand queries. |
| **Lead Gen** | Brand CPC typically lower ($0.30–$1.50); cannibalization test via geo-split is essential since organic has higher relative CTR. |
| **High spend (>$50K/mo)** | Must run incrementality testing (geo-split or time-based on/off) to quantify cannibalization; brand campaigns are a governance layer. |
| **Low spend (<$5K/mo)** | Brand campaigns may be optional if: unique brand name, clean SERP, no competitor conquesting. Test before removing. |
| **Generic/ambiguous brand names** | Brand defense is critical; auction pressure high. Consider broader match types on brand campaign. |

### Sources

- VIDEN: videnglobe.com/blog/branded-vs-non-branded-keywords (150+ account audit findings)
- PPC Pitbulls: ppcpitbulls.com/blog/why-you-need-to-separate-brand-and-non-brand-results-in-google-ads
- Perfoads brand/non-brand segmentation guide
- Search South brand separation analysis

---

## Domain 2: Non-Branded Search Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Quality Score on keywords with >$100/mo spend | QS ≤5 | Investigate and restructure |
| Quality Score on core commercial keywords | QS ≥7 | Working standard; no action needed |
| QS 7+ vs QS 5 CPC difference | 35–60% higher CPC at QS 5 | Concrete example: QS 8 = €2.80 CPC vs QS 5 = €4.50 CPC (same keyword) |
| Negative-to-active keyword ratio | <0.20 (fewer than 1 negative per 5 active keywords) | Flag as "poor negative hygiene" |
| Negative-to-active ratio benchmark | 0.30–0.50 for mature accounts | Healthy ratio for established accounts |
| Match type migration dip (Broad → Exact transition) | 15–30% performance dip for 2–4 weeks | Expected; do not panic-revert during this window |
| Keyword fatigue | CTR decline >20% over 8 weeks on stable-volume keyword | Flag for refresh/restructure |
| Search term to keyword ratio | >5:1 search terms per keyword (broad match) | Negative keyword mining needed |

**Quality Score prioritization framework (from TwoSquares):**
1. Sort keywords by spend descending, filter to QS <6
2. Check which QS component is Below Average (Expected CTR, Ad Relevance, Landing Page)
3. Apply targeted fix per component
4. Allow 3–4 weeks for data accumulation before re-evaluation
5. Measure impact via CPC reduction, not QS number itself

### Minimum Data Requirements

- 14 days minimum for QS stabilization after changes
- 30 days for match type migration assessment
- 100+ clicks per keyword for reliable QS evaluation
- 1,000+ impressions for CTR-based fatigue detection
- At least 50 active keywords for negative ratio to be meaningful

### Detection Logic (Pseudocode)

```python
def detect_qs_issues(account, min_monthly_spend=100):
    keywords = get_keywords(account, status='ENABLED')
    flagged = []

    for kw in keywords:
        if kw.monthly_spend < min_monthly_spend:
            continue
        if kw.quality_score <= 5:
            component_issues = []
            if kw.expected_ctr == 'BELOW_AVERAGE':
                component_issues.append('expected_ctr')
            if kw.ad_relevance == 'BELOW_AVERAGE':
                component_issues.append('ad_relevance')
            if kw.landing_page_experience == 'BELOW_AVERAGE':
                component_issues.append('landing_page')

            cpc_premium = estimate_cpc_premium(kw.quality_score)
            wasted_spend = kw.monthly_spend * (cpc_premium / (1 + cpc_premium))

            flagged.append({
                'keyword': kw.text,
                'qs': kw.quality_score,
                'issues': component_issues,
                'monthly_spend': kw.monthly_spend,
                'estimated_waste': wasted_spend
            })

    return sorted(flagged, key=lambda x: x['estimated_waste'], reverse=True)


def estimate_cpc_premium(qs):
    """Estimated CPC premium relative to QS 8 baseline."""
    premiums = {1: 4.0, 2: 2.5, 3: 1.8, 4: 1.2, 5: 0.60, 6: 0.25, 7: 0.10, 8: 0.0, 9: -0.10, 10: -0.15}
    return premiums.get(qs, 0.0)


def detect_negative_keyword_hygiene(account):
    campaigns = get_campaigns(account, type='SEARCH')
    for campaign in campaigns:
        active_kw_count = len(get_keywords(campaign, status='ENABLED'))
        negative_kw_count = len(get_negative_keywords(campaign))
        ratio = negative_kw_count / max(active_kw_count, 1)

        if ratio < 0.20:
            yield Alert("LOW_NEGATIVE_HYGIENE", campaign=campaign.name,
                        details=f"Ratio {ratio:.2f} — below 0.20 minimum. "
                                f"Active: {active_kw_count}, Negatives: {negative_kw_count}")


def detect_match_type_migration_dip(account, campaign_id, migration_date):
    pre_period = get_metrics(campaign_id, start=migration_date - days(28), end=migration_date)
    post_period = get_metrics(campaign_id, start=migration_date, end=migration_date + days(28))

    cpa_change = (post_period.cpa - pre_period.cpa) / pre_period.cpa
    conv_change = (post_period.conversions - pre_period.conversions) / pre_period.conversions

    if cpa_change > 0.30 and (migration_date + days(28)) > today():
        return Alert("MIGRATION_DIP_IN_PROGRESS",
                     details=f"CPA up {cpa_change:.0%} — within expected 2-4 week dip window")
    elif cpa_change > 0.30 and (today() - migration_date).days > 42:
        return Alert("MIGRATION_DIP_EXTENDED", severity="high",
                     details="Performance hasn't recovered 6+ weeks post-migration")

    return None


def detect_keyword_fatigue(account, lookback_weeks=8):
    keywords = get_keywords(account, min_impressions_per_week=200)
    for kw in keywords:
        ctr_series = get_weekly_ctr(kw, weeks=lookback_weeks)
        if len(ctr_series) < lookback_weeks:
            continue
        ctr_decline = (ctr_series[0] - ctr_series[-1]) / ctr_series[0]
        if ctr_decline > 0.20 and kw.impression_volume_stable():
            yield Alert("KEYWORD_FATIGUE", keyword=kw.text,
                        details=f"CTR declined {ctr_decline:.0%} over {lookback_weeks} weeks")
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | QS matters less for Shopping (no keyword-level QS); focus on Search campaigns. Negative hygiene critical for broad match + Smart Bidding. |
| **Lead Gen** | QS 5–6 on competitive terms (legal, finance) is acceptable due to high CPCs; threshold shifts to QS ≤4 for action. |
| **High spend** | Marginal CPA analysis needed (ALM Corp): blended metrics hide diminishing returns on last $50K of spend. |
| **Low spend (<$5K/mo)** | Manual CPC may outperform Smart Bidding when <30 conversions/month. |
| **Broad match accounts** | Negative-to-active ratio should be 0.50+ to compensate for query expansion. Monitor search term report weekly. |

### Sources

- TwoSquares: twosquares.co.uk/blog/google-ads-quality-score-guide (QS framework, prioritization)
- ALM Corp: almcorp.com/blog/google-search-ads-audit-2026/ (audit framework, marginal returns)
- ALM Corp: almcorp.com/blog/google-ads-manual-cpc-update-2026/ (manual vs smart bidding thresholds)
- Search Engine Land: 2026 deprecated tactics (phrase match deprecation, broad match guidance)

---

## Domain 3: Performance Max Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Shopping channel share (ecommerce PMax) | <50% of spend in Shopping | Flag as potential asset-group over-allocation to Display/YouTube |
| Shopping channel share (healthy ecommerce) | 60–80% in Shopping | Normal range |
| Minimum conversions per campaign | <30/month | Insufficient for Smart Bidding; consider intermediate conversion actions or campaign consolidation |
| Optimal conversions per campaign | 50–100/month | Algorithm operates effectively |
| Brand exclusion ROAS impact | 20–40% ROAS decrease after applying brand exclusions | Expected; measures true incremental performance |
| Asset group structure (optimal) | Multiple campaigns × 1 asset group each | Best ROAS per Optmyzr 9,199-account study |
| Asset completeness per group | 10–15 headlines, 3–5 long headlines, 5–10 descriptions, 5–10 images, 1–3 videos | Below minimums = algorithm starved for creative signals |
| PMax learning phase | 30 days initial, 6–8 weeks for full optimization | Avoid major changes during learning |
| Manual vs auto-generated video | Manual outperforms by 25–40% | Always provide custom video assets |

### Minimum Data Requirements

- 30+ conversions/month per campaign minimum (50–100 optimal)
- 14 days minimum before evaluating channel distribution
- Google Ads API access for channel-level spend data (not in UI)
- Asset group performance data requires 500+ impressions per asset for reliable signals
- 90 days for full PMax maturation assessment

### Detection Logic (Pseudocode)

```python
def detect_pmax_channel_distribution(account, campaign):
    channel_data = get_pmax_channel_report(campaign)  # requires API
    total_spend = sum(ch.cost for ch in channel_data)

    if account.vertical == 'ECOMMERCE':
        shopping_pct = channel_data.shopping.cost / total_spend
        if shopping_pct < 0.50:
            return Alert("LOW_SHOPPING_ALLOCATION", severity="high",
                         details=f"Shopping at {shopping_pct:.0%} — expected 60-80% for ecommerce. "
                                 f"Display/YouTube may be absorbing budget without conversion intent.")
        if shopping_pct > 0.90:
            return Alert("OVER_CONCENTRATED_SHOPPING", severity="medium",
                         details="PMax not utilizing upper-funnel channels; "
                                 "may be missing prospecting opportunity")

    display_pct = channel_data.display.cost / total_spend
    if display_pct > 0.40:
        return Alert("HIGH_DISPLAY_SPEND", severity="medium",
                     details=f"Display at {display_pct:.0%} — often low-quality placements")

    return None


def detect_pmax_conversion_volume(campaign):
    monthly_conversions = campaign.conversions_last_30d

    if monthly_conversions < 30:
        return Alert("INSUFFICIENT_PMAX_VOLUME", severity="high",
                     details=f"Only {monthly_conversions} conversions/30d. "
                             f"Smart Bidding cannot optimize effectively. "
                             f"Options: consolidate campaigns, use micro-conversions, "
                             f"or switch to manual bidding.")

    if monthly_conversions < 50:
        return Alert("LOW_PMAX_VOLUME", severity="medium",
                     details=f"{monthly_conversions} conversions/30d — functional but suboptimal")

    return None


def detect_pmax_asset_completeness(campaign):
    for ag in campaign.asset_groups:
        issues = []
        if ag.headline_count < 10:
            issues.append(f"Headlines: {ag.headline_count}/10 minimum")
        if ag.description_count < 5:
            issues.append(f"Descriptions: {ag.description_count}/5 minimum")
        if ag.image_count < 5:
            issues.append(f"Images: {ag.image_count}/5 minimum")
        if ag.video_count == 0:
            issues.append("No video — Google will auto-generate (25-40% worse)")

        low_performing = [a for a in ag.assets if a.performance_label == 'LOW']
        if len(low_performing) > len(ag.assets) * 0.3:
            issues.append(f"{len(low_performing)} LOW-rated assets — replace")

        if issues:
            yield Alert("ASSET_GROUP_INCOMPLETE", asset_group=ag.name,
                        details="; ".join(issues))


def detect_brand_exclusion_impact(campaign, pre_exclusion_window=30, post_exclusion_window=30):
    pre = get_metrics(campaign, period='pre_brand_exclusion', days=pre_exclusion_window)
    post = get_metrics(campaign, period='post_brand_exclusion', days=post_exclusion_window)

    roas_change = (post.roas - pre.roas) / pre.roas

    if roas_change < -0.40:
        return Alert("SEVERE_BRAND_EXCLUSION_IMPACT", severity="high",
                     details=f"ROAS dropped {abs(roas_change):.0%} — campaign may have been "
                             f"primarily converting brand demand")
    elif -0.40 <= roas_change <= -0.20:
        return Alert("EXPECTED_BRAND_EXCLUSION_IMPACT", severity="info",
                     details=f"ROAS dropped {abs(roas_change):.0%} — within expected 20-40% range")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Feed-only PMax (no text/image assets) limits to Shopping+Display channels — useful for isolating Shopping performance. Product feed quality is the #1 lever. |
| **Lead Gen** | PMax should allocate more to Search/YouTube; Shopping irrelevant. Conversion signal quality critical — use intermediate goals (form start) if lead volume is low. |
| **High spend (>$50K/mo)** | Run hybrid: Standard Shopping for high-control products + PMax for prospecting. Address zombie inventory (<10 clicks/month) via separate Standard Shopping. |
| **Low spend (<$10K/mo)** | Single campaign, single asset group ("Starter" structure). Avoid splitting budget across multiple PMax campaigns below 30 conversions/month each. |
| **Multi-product ecommerce** | Segment by margin via custom labels. Prevent high-performers from monopolizing budget using listing group subdivision. |

### Sources

- smarter-ecommerce.com: PMax channel report deep dive, hybrid Shopping strategy (€500M+ ad spend data)
- Optmyzr: Performance Max study (9,199 accounts) — optmyzr.com/blog/performance-max-study
- Store Growers: storegrowers.com/performance-max-campaigns (ecommerce guide)
- GROAS: groas.ai (April 2026 updates, creative strategy)
- Digital Applied: PMax 2026 campaign guide

---

## Domain 4: YouTube / Video Campaign Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| View-through rate (skippable in-stream) | <25% | Hook/creative issue — test new opening 5 seconds |
| VTR benchmark (skippable in-stream) | 30–40% (mobile) | Healthy range |
| VTR (Connected TV) | 95%+ completion | Non-skippable by nature; focus on brand lift metrics |
| VTR (YouTube Shorts) | 3x higher completion vs repurposed landscape | Native Shorts content significantly outperforms |
| 5-second branding rule | Brand absent in first 5 seconds | 40% lower VTR; always brand before skip button |
| Creative fatigue onset (YouTube) | CTR decline >10% WoW OR CPV increase >20% over 3 days | Refresh hooks first (restores 60–80% of performance) |
| Creative fatigue timeline (YouTube) | 4–8 weeks typical | Longer than social platforms (Meta: 2–4 weeks, TikTok: 3–7 days) |
| Frequency threshold (cold audiences) | >2.5 | Audience saturation; expand targeting or rotate creative |
| Hook rate / Thumbstop ratio | <20% | Creative isn't stopping the scroll; test new hooks |
| Top 10% vs average creative | 3.2x better results | Creative quality is the primary performance lever |

**Hook framework VTR benchmarks:**
- Question Hook ("Ever wondered why…?"): 35–45% VTR (curiosity-driven)
- Bold Statement: 30–40% VTR (polarizing, high engagement)
- Pattern Interrupt (visual/audio): 40–50% VTR (highest attention capture)
- Direct Address ("You're doing X wrong"): 30–35% VTR (targeted)
- Result Preview ("We generated $1M in…"): 35–40% VTR (proof-driven)

### Minimum Data Requirements

- 5,000+ impressions per creative for VTR reliability
- 14 days minimum for creative fatigue detection
- 3+ creative variants running simultaneously for A/B validity
- 100+ conversions per format for funnel-stage attribution
- Weekly creative production cadence for sustained campaigns

### Detection Logic (Pseudocode)

```python
def detect_creative_fatigue(campaign, lookback_days=14):
    creatives = get_video_assets(campaign)
    for creative in creatives:
        metrics = get_daily_metrics(creative, days=lookback_days)

        ctr_series = [m.ctr for m in metrics]
        cpv_series = [m.cpv for m in metrics]

        # Week-over-week CTR decline
        week1_ctr = mean(ctr_series[:7])
        week2_ctr = mean(ctr_series[7:14])
        ctr_decline = (week1_ctr - week2_ctr) / week1_ctr if week1_ctr > 0 else 0

        # 3-day CPV spike
        recent_cpv = mean(cpv_series[-3:])
        baseline_cpv = mean(cpv_series[:7])
        cpv_increase = (recent_cpv - baseline_cpv) / baseline_cpv if baseline_cpv > 0 else 0

        if ctr_decline > 0.10 or cpv_increase > 0.20:
            age_days = creative.days_since_launch
            return Alert("CREATIVE_FATIGUE",
                         creative=creative.id,
                         severity="high" if ctr_decline > 0.15 else "medium",
                         details=f"CTR down {ctr_decline:.0%}, CPV up {cpv_increase:.0%} "
                                 f"after {age_days} days. Refresh hooks first.")

    return None


def detect_branding_compliance(creative):
    if creative.brand_appearance_seconds > 5:
        return Alert("LATE_BRANDING",
                     details="Brand doesn't appear in first 5 seconds — "
                             "expect ~40% lower VTR")
    return None


def detect_format_funnel_misalignment(campaign):
    format_funnel_map = {
        'SKIPPABLE_IN_STREAM': ['awareness', 'consideration'],
        'NON_SKIPPABLE_IN_STREAM': ['awareness'],
        'BUMPER_6S': ['awareness', 'recall'],
        'IN_FEED_VIDEO': ['consideration'],
        'SHORTS': ['awareness', 'consideration'],
        'VIDEO_ACTION': ['conversion'],
    }

    campaign_objective = campaign.objective  # awareness|consideration|conversion
    format_type = campaign.video_format

    expected_stages = format_funnel_map.get(format_type, [])
    if campaign_objective not in expected_stages:
        return Alert("FORMAT_FUNNEL_MISMATCH",
                     details=f"Format {format_type} optimized for {expected_stages}, "
                             f"but campaign targets {campaign_objective}")

    return None


def assess_creative_velocity(account):
    active_creatives = get_active_video_creatives(account)
    creatives_launched_last_30d = [c for c in active_creatives if c.age_days <= 30]

    if len(creatives_launched_last_30d) < 3:
        return Alert("LOW_CREATIVE_VELOCITY",
                     details=f"Only {len(creatives_launched_last_30d)} new creatives in 30 days. "
                             f"Minimum 3-5 new variants/month to prevent portfolio fatigue.")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | YouTube Shopping integration (auto-tagging via computer vision) enables shoppable ads. Focus on Video Action campaigns for direct conversion. Shorts up to 3x completion vs landscape. |
| **Lead Gen / B2B** | Longer-form (2–5 min) educational content for consideration. VTR benchmarks lower (20–30%) but qualified view value higher. |
| **DTC / Brand** | Creative velocity is bottleneck: traditional production = 3–5 weeks/$3K–$15K per 30s video. AI generation cuts to hours/60% lower cost. Target 6–12 variants/quarter minimum. |
| **High spend** | Portfolio approach: 10–20 low-fidelity variations weekly instead of single hero videos. |
| **Low spend** | Focus on 1–2 formats only (Shorts + skippable in-stream). Don't spread thin across all formats. |

### Sources

- Digital Applied: digitalapplied.com/blog/youtube-ads-2026-video-advertising-strategy-guide
- GROAS: groas.ai/post/youtube-ads-updates-what-changed-in-early-2026
- Creatify: creatify.ai (YouTube ads guide 2026)
- Koro: getkoro.app/blog/creative-fatigue-detection-guide-2026
- AdBid: adbid.me/blog/ad-creative-testing-guide-2026
- PxlPeak: pxlpeak.com/blog/google-ads/youtube-ads-complete-guide-2026

---

## Domain 5: Shopping / Product Feed Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Title optimization CTR lift | +18% average, +88% with exact query match | Prioritize title rewrites for top-spend products |
| Title optimization conversion lift | +95% (brand+product type added) | Documented case study result |
| Title structure | [Brand] + [Product Type] + [Key Attributes] + [Color/Size] | Front-load important keywords (Google truncates in ads) |
| Title length | 150 characters max, use all available space | Short titles = missed ranking signals |
| Product type in title | +10% conversion rate when added | Low-effort, high-impact optimization |
| Custom label utilization | 0 custom labels used | Flag as "unsegmented feed" — missing bid/budget control |
| Zombie products (PMax) | <10 clicks/month per product | Route to Standard Shopping catch-all campaign |
| Price competitiveness | Priced >20% above median for category | Reduced Shopping impression share; feed quality can't fully compensate |
| Stock-out rate | >5% of feed products out of stock | Cascading effect: budget reallocates to remaining products, CPC rises |
| Feed attribute completeness | <90% of attributes populated | Baseline issue — fix before optimization |

**Title optimization priority order:**
1. Add missing attributes (GTIN, brand, color, size, material)
2. Optimize product descriptions
3. Rewrite titles with [Brand] + [Product Type] + [Attributes] formula
4. Apply custom labels (margin, performance tier, seasonality)

### Minimum Data Requirements

- 30 days of Shopping data for product-level performance
- 500+ products for meaningful segmentation via custom labels
- Click data per product (minimum 50 clicks for individual product optimization)
- Competitive pricing data from Google Merchant Center price benchmarks
- Feed diagnostic report from Merchant Center for attribute completeness

### Detection Logic (Pseudocode)

```python
def detect_title_optimization_opportunities(feed):
    opportunities = []
    for product in feed.products:
        title_issues = []
        if product.brand not in product.title:
            title_issues.append('missing_brand')
        if product.product_type_l1 not in product.title.lower():
            title_issues.append('missing_product_type')
        if len(product.title) < 80:
            title_issues.append('short_title')
        if product.color and product.color not in product.title:
            title_issues.append('missing_color')
        if product.size and product.size not in product.title:
            title_issues.append('missing_size')

        if title_issues and product.monthly_spend > 50:
            opportunities.append({
                'product_id': product.id,
                'current_title': product.title,
                'issues': title_issues,
                'monthly_spend': product.monthly_spend,
                'estimated_ctr_lift': 0.18 * len(title_issues) / 5
            })

    return sorted(opportunities, key=lambda x: x['monthly_spend'], reverse=True)


def detect_zombie_products(account, threshold_clicks=10):
    products = get_product_performance(account, days=30)
    zombies = [p for p in products if p.clicks < threshold_clicks and p.impressions > 100]

    if len(zombies) > len(products) * 0.30:
        return Alert("HIGH_ZOMBIE_RATE",
                     details=f"{len(zombies)}/{len(products)} products ({len(zombies)/len(products):.0%}) "
                             f"receiving <{threshold_clicks} clicks/month. "
                             f"Route to Standard Shopping catch-all campaign.")
    return None


def detect_custom_label_usage(campaign):
    products = get_listing_groups(campaign)
    labels_used = set()
    for p in products:
        for i in range(5):
            if getattr(p, f'custom_label_{i}', None):
                labels_used.add(i)

    if len(labels_used) == 0:
        return Alert("NO_CUSTOM_LABELS", severity="high",
                     details="No custom labels in use — cannot segment by margin, "
                             "performance, or seasonality")

    recommended_labels = ['margin_tier', 'performance_tier', 'seasonality', 'price_tier']
    missing = [l for l in recommended_labels if l not in get_label_strategies(campaign)]

    if missing:
        return Alert("MISSING_LABEL_STRATEGIES", severity="medium",
                     details=f"Missing segmentation: {', '.join(missing)}")

    return None


def detect_price_competitiveness(product, merchant_center_benchmarks):
    benchmark_price = merchant_center_benchmarks.get(product.id)
    if not benchmark_price:
        return None

    price_ratio = product.price / benchmark_price
    if price_ratio > 1.20:
        return Alert("PRICE_UNCOMPETITIVE",
                     product=product.id,
                     details=f"Priced {price_ratio:.0%} of category median — "
                             f"expect reduced impression share")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Fashion/Apparel** | Title formula: [Brand] + [Gender] + [Product Type] + [Material] + [Color] + [Size]. Color and size are critical ranking signals. |
| **Electronics** | Title formula: [Brand] + [Model Number] + [Key Spec] + [Year]. Model numbers and specs drive exact-match queries. |
| **Home/Garden** | Title formula: [Brand] + [Product Type] + [Material] + [Dimensions]. Dimensions and material differentiate products. |
| **High-margin products** | Assign custom_label_0 = 'high_margin', set higher bids via listing group subdivision. |
| **Clearance/seasonal** | Assign custom_label_1 = 'clearance', run in separate Standard Shopping for aggressive bidding without polluting PMax. |

### Sources

- Channable: channable.com/blog/pmax-campaign-segmentation (custom label strategy)
- DataFeedWatch: datafeedwatch.com (title optimization rules, +250% click increase case study)
- k-sync: sync.krokanti.com/en/blog/product-feed-optimization-google-shopping-guide
- tenten.co: Google Shopping feed optimization (title structure, price competitiveness)

---

## Domain 6: Bidding Strategy Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Maximize Conversions → tCPA transition | 30+ conversions/30 days minimum | Below 30 = premature transition, algorithm unstable |
| tCPA transition (confident) | 50+ conversions/30 days | Strong data foundation for Smart Bidding |
| Maximize Conversions → tROAS transition | 50+ conversions/30 days | Google's official recommendation |
| Initial target CPA setting | Within 20–30% above current average CPA | Setting too aggressively low causes volume collapse |
| Initial target ROAS setting | Within 20–30% of current achieved ROAS | Start conservative, tighten over 2–4 week cycles |
| Learning phase duration | 3 conversion cycles OR 4 weeks (whichever longer) | Do not adjust during this window |
| Manual CPC viable threshold | <30 conversions/month OR <$2,000/month budget | Smart Bidding underperforms in low-data environments |
| Portfolio vs Standard bidding | Portfolio = shared budget across campaigns; Standard = per-campaign | Portfolio limited: incompatible with broad match A/B testing |
| Target adjustment cadence | Every 2–4 weeks, ≤10–15% per adjustment | Larger jumps re-trigger learning phase |
| Marginal CPA crossover | When last 20% of spend produces >2x average CPA | Diminishing returns threshold — reduce budget or reallocate |

**Anti-pattern flags:**
1. Setting tCPA below current average CPA immediately after transition → volume collapse
2. Switching bidding strategy during seasonal peaks → learning phase during critical period
3. Running tROAS with <50 conversions/month → unstable optimization
4. Using phrase match with Smart Bidding in 2026 → phrase match deprecated in favor of broad
5. Over-relying on GA4 as primary conversion action → use native Google Ads conversion tags

### Minimum Data Requirements

- 30 days of conversion data before strategy transition
- 2–3 conversion cycles post-transition before evaluation
- Conversion delay mapping (know your actual delay: 1 day? 7 days? 30 days?)
- At least 3 months of historical CPA/ROAS data for target-setting baseline
- Minimum $2,000/month budget for Smart Bidding effectiveness

### Detection Logic (Pseudocode)

```python
def detect_premature_bidding_transition(campaign):
    strategy = campaign.bidding_strategy
    strategy_age_days = campaign.days_since_strategy_change
    monthly_conversions = campaign.conversions_last_30d

    if strategy.type in ('TARGET_CPA', 'TARGET_ROAS'):
        if monthly_conversions < 30:
            return Alert("PREMATURE_SMART_BIDDING", severity="high",
                         details=f"Campaign has {monthly_conversions} conversions/30d on "
                                 f"{strategy.type}. Minimum 30 required (50 recommended). "
                                 f"Revert to Maximize Conversions or Manual CPC.")

        if strategy.type == 'TARGET_ROAS' and monthly_conversions < 50:
            return Alert("LOW_VOLUME_TROAS", severity="medium",
                         details=f"tROAS with only {monthly_conversions} conversions/30d — "
                                 f"Google recommends 50+ for tROAS stability")

    return None


def detect_aggressive_target_setting(campaign):
    strategy = campaign.bidding_strategy
    if strategy.type == 'TARGET_CPA':
        historical_cpa = campaign.avg_cpa_prior_90d
        target_cpa = strategy.target_cpa
        gap = (historical_cpa - target_cpa) / historical_cpa

        if gap > 0.30:
            return Alert("AGGRESSIVE_TCPA",
                         details=f"Target CPA ${target_cpa:.2f} is {gap:.0%} below "
                                 f"historical average ${historical_cpa:.2f}. "
                                 f"Risk of volume collapse. Set within 20-30% of historical.")

    if strategy.type == 'TARGET_ROAS':
        historical_roas = campaign.avg_roas_prior_90d
        target_roas = strategy.target_roas
        gap = (target_roas - historical_roas) / historical_roas

        if gap > 0.30:
            return Alert("AGGRESSIVE_TROAS",
                         details=f"Target ROAS {target_roas:.0%} is {gap:.0%} above "
                                 f"historical {historical_roas:.0%}. Risk of underspend.")

    return None


def detect_diminishing_returns(account, campaign):
    spend_deciles = get_spend_deciles(campaign, days=30)
    last_decile_cpa = spend_deciles[-1].cpa
    overall_cpa = campaign.cpa_last_30d

    if last_decile_cpa > overall_cpa * 2:
        wasted = spend_deciles[-1].cost
        return Alert("DIMINISHING_RETURNS", severity="high",
                     details=f"Last 10% of spend (${wasted:.0f}) producing CPA "
                             f"${last_decile_cpa:.2f} — {last_decile_cpa/overall_cpa:.1f}x "
                             f"the account average. Reallocate or reduce.")

    return None


def detect_learning_phase_disruption(campaign, lookback_days=30):
    changes = get_campaign_changes(campaign, days=lookback_days)
    strategy_changes = [c for c in changes if c.type == 'BIDDING_STRATEGY']
    target_changes = [c for c in changes if c.type in ('TARGET_CPA_CHANGE', 'TARGET_ROAS_CHANGE')]

    if len(strategy_changes) > 1:
        return Alert("FREQUENT_STRATEGY_CHANGES",
                     details=f"{len(strategy_changes)} bidding strategy changes in 30 days — "
                             f"each re-triggers learning phase")

    large_adjustments = [c for c in target_changes
                         if abs(c.pct_change) > 0.15]
    if len(large_adjustments) > 2:
        return Alert("FREQUENT_TARGET_ADJUSTMENTS",
                     details=f"{len(large_adjustments)} adjustments >15% in 30 days")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | tROAS preferred over tCPA; set initial target at 80% of current ROAS. Portfolio bidding across product categories can work if total conversions >100/month. |
| **Lead Gen** | tCPA preferred; account for lead quality variation. Set tCPA based on qualified lead CPA, not raw form-fill CPA. |
| **High spend (>$100K/mo)** | Marginal CPA analysis essential. Use portfolio bidding to let algorithm reallocate across campaigns. Monitor last-decile efficiency. |
| **Low spend (<$5K/mo)** | Manual CPC often outperforms. If using Smart Bidding, Maximize Conversions without a target is safer than setting tCPA/tROAS with insufficient data. |
| **Seasonal accounts** | Use Seasonality Adjustments to signal expected conversion rate changes rather than changing bid strategy during peaks. |

### Sources

- Google Ads Help: support.google.com/google-ads/answer/14573087 (bidding transitions)
- Google Ads Help: support.google.com/google-ads/answer/6268633 (Smart Bidding measurement)
- ALM Corp: almcorp.com/blog/google-ads-manual-cpc-update-2026/ (manual CPC thresholds)
- ALM Corp: almcorp.com/blog/google-search-ads-audit-2026/ (marginal returns analysis)
- GrowMyAds: growmyads.com/switch-from-maximize-conversions-to-target-cpa/
- Adnan Agic: adnanagic.com/blog/google-ads-bidding-strategy-transitions/

---

## Domain 7: Campaign Structure Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Minimum conversions per campaign | 30–50/month | Below this = consolidate campaigns |
| Consolidation trigger | <30 conversions/month per campaign | Merge related campaigns to feed Smart Bidding sufficient data |
| Segmentation threshold | >50 conversions/month per resulting segment | Only segment when each new campaign can sustain this volume |
| Maximum keywords per ad group | 15–20 | Beyond this = relevance drops, QS suffers |
| Ideal keyword-to-ad-group ratio | 5–10 tightly themed keywords per ad group | "One intent per ad group" principle |
| Account structure tiers | Determined by monthly conversion volume | See templates below |
| Deprecated: SKAG (single keyword ad groups) | Obsolete in 2026 Smart Bidding era | Fragments data; prevents algorithm learning |
| Deprecated: granular device segmentation | Removed by Google | Use bid adjustments instead of separate campaigns |

**Structure templates by account size:**

| Account Tier | Monthly Conversions | Recommended Structure |
|-------------|--------------------|-----------------------|
| Starter | <50 | 1 Search + 1 PMax campaign. Maximize Conversions, no target. Single ad group per intent theme. |
| Growth | 50–200 | Brand Search + Non-Brand Search (2–3 ad groups) + 1 PMax. Transition to tCPA/tROAS. |
| Scale | 200–1,000 | Brand Search + Non-Brand by intent tier + PMax by product/service category + Demand Gen for upper funnel. Portfolio bidding. |
| Enterprise | 1,000+ | Full funnel: Brand + Non-Brand (segmented by match type) + Standard Shopping (control) + PMax (prospecting) + YouTube + Demand Gen. Marginal CPA analysis per campaign. |

### Minimum Data Requirements

- 90 days of account history for structure assessment
- Conversion volume per campaign per month
- Ad group-level performance data (CTR, CPA, conversion rate)
- Search term reports for ad group theme validation
- At least 30 days post-restructure for performance comparison

### Detection Logic (Pseudocode)

```python
def detect_structure_issues(account):
    campaigns = get_campaigns(account, status='ENABLED')
    issues = []

    # Check for fragmentation
    low_volume_campaigns = [c for c in campaigns
                            if c.conversions_last_30d < 30 and c.cost_last_30d > 0]

    if len(low_volume_campaigns) > len(campaigns) * 0.50:
        total_conv = sum(c.conversions_last_30d for c in campaigns)
        issues.append(Alert("OVER_FRAGMENTED",
                            details=f"{len(low_volume_campaigns)}/{len(campaigns)} campaigns "
                                    f"below 30 conversions/month. Total account conversions: "
                                    f"{total_conv}. Consolidate to feed Smart Bidding."))

    # Check for SKAGs
    for campaign in campaigns:
        for ag in campaign.ad_groups:
            kw_count = len(get_keywords(ag))
            if kw_count == 1:
                issues.append(Alert("SKAG_DETECTED", ad_group=ag.name,
                                    details="Single-keyword ad groups are deprecated in 2026. "
                                            "Consolidate into intent-themed groups of 5-10 keywords."))

    # Check for missing brand separation
    has_brand_campaign = any(c.name_contains('brand') for c in campaigns)
    has_pmax = any(c.type == 'PERFORMANCE_MAX' for c in campaigns)

    if has_pmax and not has_brand_campaign:
        issues.append(Alert("NO_BRAND_SEPARATION",
                            details="PMax running without dedicated Brand Search campaign — "
                                    "brand demand leaking to PMax"))

    return issues


def recommend_structure(account):
    total_conversions = account.conversions_last_30d

    if total_conversions < 50:
        return StructureTemplate("STARTER",
                                 campaigns=['search_all', 'pmax'],
                                 bidding='maximize_conversions',
                                 notes="Single Search + single PMax. "
                                       "No target until 50+ conversions/month.")

    elif total_conversions < 200:
        return StructureTemplate("GROWTH",
                                 campaigns=['brand_search', 'nonbrand_search', 'pmax'],
                                 bidding='target_cpa',
                                 notes="Separate brand. 2-3 ad groups per non-brand theme. "
                                       "Transition to tCPA when each campaign hits 30+/month.")

    elif total_conversions < 1000:
        return StructureTemplate("SCALE",
                                 campaigns=['brand_search', 'nonbrand_intent_tiers',
                                            'pmax_by_category', 'demand_gen'],
                                 bidding='portfolio_target_roas',
                                 notes="Segment non-brand by intent (high/medium/low). "
                                       "Multiple PMax by product category. Portfolio bidding.")

    else:
        return StructureTemplate("ENTERPRISE",
                                 campaigns=['brand_search', 'nonbrand_exact', 'nonbrand_broad',
                                            'standard_shopping', 'pmax_prospecting',
                                            'youtube', 'demand_gen'],
                                 bidding='portfolio_target_roas',
                                 notes="Full funnel. Standard Shopping for control + "
                                       "PMax for prospecting. Marginal CPA analysis per campaign.")
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Shopping/PMax campaigns are primary revenue drivers. Structure around product categories via feed segmentation, not keyword themes. |
| **Lead Gen** | Structure by funnel stage: awareness (Display/YouTube), consideration (non-brand Search), conversion (brand Search + high-intent). Lead quality tracking essential. |
| **Local / multi-location** | Location-based campaign segmentation justified when each location generates 30+ conversions/month. Otherwise, consolidate with location bid adjustments. |
| **B2B with long sales cycles** | Use micro-conversions (form views, content downloads) to boost campaign conversion volume above 30/month threshold for Smart Bidding. |

### Sources

- LeadsBridge: leadsbridge.com/blog/google-ads-campaign-structure/ (structure guide)
- ALM Corp: almcorp.com/blog/google-search-ads-audit-2026/ (advanced structure tactics)
- Search Engine Land: deprecated tactics (SKAGs, phrase match)
- Optmyzr: PMax structure study (Starter/Focused/Conversion-Hungry/Mixed taxonomy)

---

## Domain 8: SEO x Paid Search Interaction

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Organic rank decline trigger | Drop from position 1–3 to position 4–10 on high-value term | Increase paid bid/budget on affected terms within 48 hours |
| SERP doubling effect | Running paid + organic = 91% more paid clicks (when cited in AI Overview) | Maintain both presence channels on core terms |
| AI Overview presence | 25.56% of SERPs now show AI Overviews | Monitor AIO citation status for brand and category terms |
| Organic CTR decline (AIO queries) | -61% organic CTR on queries with AI Overviews | Increase paid investment on AIO-affected queries |
| Organic CTR decline (non-AIO queries) | -41% organic CTR even without AI Overviews | Systemic SERP shift toward paid; adjust budgets |
| Paid click increase | +100% (doubled) paid search clicks YoY in product verticals | Budget planning must account for organic → paid migration |
| Zero-click rate | 58.5% of US searches (77.2% mobile) | Accept reduced organic traffic; invest in paid presence |
| Cannibalization detection | Pause branded paid → organic doesn't capture >85% of lost paid clicks | Brand paid is incremental; maintain investment |
| Brand AIO citation impact | Cited = +91% paid clicks, +35% organic clicks; Not cited = -78% paid CTR | AIO citation status is a new critical monitoring dimension |

### Minimum Data Requirements

- Google Search Console API access for organic rank/CTR data
- Google Ads data matched by keyword/query to organic performance
- 90 days of parallel paid + organic data for interaction modeling
- Weekly rank tracking for top 50–100 non-brand keywords
- AIO monitoring (via SERP tracking tools) for brand and category terms

### Detection Logic (Pseudocode)

```python
def detect_organic_decline_trigger(account, gsc_data):
    high_value_keywords = get_high_value_keywords(account, min_monthly_value=500)

    for kw in high_value_keywords:
        organic_rank = gsc_data.get_avg_position(kw.text, days=7)
        organic_rank_prior = gsc_data.get_avg_position(kw.text, days=7, offset=7)

        if organic_rank_prior <= 3 and organic_rank > 3:
            paid_coverage = get_paid_impression_share(account, kw.text)
            yield Alert("ORGANIC_RANK_DROP",
                        keyword=kw.text,
                        severity="high",
                        details=f"Organic dropped from position {organic_rank_prior:.1f} to "
                                f"{organic_rank:.1f}. Paid impression share: {paid_coverage:.0%}. "
                                f"Recommend increasing paid bid by 20-30% on this term.")


def detect_serp_doubling_opportunity(account, gsc_data):
    """Find terms where adding/maintaining paid presence alongside organic doubles CTR."""
    organic_top3 = gsc_data.get_keywords(max_position=3)

    for kw in organic_top3:
        paid_coverage = get_paid_impression_share(account, kw.text)
        if paid_coverage < 0.50:
            organic_clicks = gsc_data.get_clicks(kw.text, days=30)
            estimated_incremental = organic_clicks * 0.50  # ~50% incremental from paid
            yield Alert("SERP_DOUBLING_OPPORTUNITY",
                        keyword=kw.text,
                        details=f"Organic position {gsc_data.get_avg_position(kw.text):.1f} "
                                f"but paid IS only {paid_coverage:.0%}. "
                                f"Estimated incremental clicks: {estimated_incremental:.0f}/month")


def detect_aio_impact(account, serp_data):
    """Monitor AI Overview impact on paid + organic performance."""
    for kw in get_tracked_keywords(account):
        aio_present = serp_data.has_ai_overview(kw.text)
        brand_cited = serp_data.brand_cited_in_aio(kw.text, account.brand_name)

        if aio_present and not brand_cited:
            yield Alert("AIO_NOT_CITED", severity="high",
                        keyword=kw.text,
                        details="AI Overview present but brand not cited — "
                                "expect -78% paid CTR and -65% organic CTR. "
                                "Increase paid bid significantly and invest in content for AIO citation.")

        if aio_present and brand_cited:
            yield Alert("AIO_CITED_POSITIVE", severity="info",
                        keyword=kw.text,
                        details="AI Overview present with brand citation — "
                                "expect +91% paid clicks, +35% organic clicks multiplier")


def detect_cannibalization(account, test_period_days=14):
    """Run when brand paid ads are paused to measure true incrementality."""
    pre_pause = get_metrics(account, period='pre_pause', days=test_period_days)
    during_pause = get_metrics(account, period='during_pause', days=test_period_days)

    paid_clicks_lost = pre_pause.brand_paid_clicks - 0
    organic_clicks_gained = during_pause.brand_organic_clicks - pre_pause.brand_organic_clicks
    recovery_rate = organic_clicks_gained / paid_clicks_lost if paid_clicks_lost > 0 else 0

    if recovery_rate < 0.85:
        return Alert("BRAND_PAID_INCREMENTAL",
                     details=f"Only {recovery_rate:.0%} of paid clicks recovered by organic. "
                             f"Brand paid ads are {1-recovery_rate:.0%} incremental. "
                             f"Maintain brand paid investment.")
    else:
        return Alert("BRAND_PAID_CANNIBALIZATION",
                     details=f"{recovery_rate:.0%} recovery — brand paid may be cannibalizing organic. "
                             f"Consider reducing brand bids.")
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Shopping results dominate SERPs; organic text results less visible. Focus on Shopping + AIO citation. Organic click share dropped from 73% to 50% in product verticals. |
| **Lead Gen / B2B** | Organic still strong for informational queries. SERP doubling most valuable for high-intent commercial terms. |
| **Local** | Google Maps/Local Pack takes SERP real estate. Paid presence critical when organic map pack ranking fluctuates. |
| **Brand-dominant** | If brand SERP is clean (no competitors, no third parties), brand paid may be less incremental. Test with geo-split. |
| **Competitive markets** | Competitor conquesting on brand terms makes paid defense essential regardless of organic rank. |

### Sources

- ALM Corp: almcorp.com/blog/paid-search-clicks-double-organic-clicks-fall-2026-data
- Authority Tech: authoritytech.io (AI citation multiplier audit)
- Seer Interactive: seerinteractive.com/insights/aio-impact-on-google-ctr-2026-update
- Paul Still: pauljstill.com (synthetic shift in search)
- VIDEN: videnglobe.com (brand search protection in AI era)

---

## Domain 9: Landing Page & Conversion Rate Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| LCP (Largest Contentful Paint) | >2.5 seconds | Flag as "Needs Improvement" — expect 30-50% QS penalty on CPC |
| LCP (critical threshold) | >4.0 seconds | "Poor" — expect significant QS degradation and 40-53% mobile bounce |
| INP (Interaction to Next Paint) | >200ms | "Needs Improvement" — impairs form interaction speed |
| INP (critical) | >500ms | "Poor" — interactive elements feel broken |
| CLS (Cumulative Layout Shift) | >0.1 | "Needs Improvement" — elements shifting degrades user trust |
| 1-second load delay | -7% to -20% conversions | Every second matters |
| Mobile bounce rate (>3s load) | 40–53% abandon | Mobile experience is the primary conversion bottleneck |
| Mobile vs desktop CVR gap | Mobile 35–42% lower than desktop | Mobile: 1.82% avg vs Desktop: 3.14% avg |
| Message match CVR lift | 2–3x (up to +212%) | Landing page headline must mirror ad copy and search query |
| Message match bounce rate reduction | -20% to -40% | Instant relevance signal |
| Form field reduction impact | +7–10% conversions per field removed | Each field is friction |
| Optimal lead gen form | Name + Email + 1 qualifying question | ~25% CVR vs ~10% with 5+ fields |
| Phone number field impact | -20% CVR when added | Highest-friction field — remove unless essential |
| Optimized LP vs homepage CVR | 5–15% vs 1–3% | 2–5x improvement from dedicated landing pages |
| QS impact of page speed | LCP 1.8s → QS 8 (€2.80 CPC) vs LCP 5.2s → QS 5 (€4.50 CPC) | Direct CPC cost from slow pages |

### Minimum Data Requirements

- Core Web Vitals data from Chrome User Experience Report (CrUX) or Lighthouse
- 1,000+ landing page sessions for reliable CVR measurement
- Mobile vs desktop segmentation in analytics
- A/B testing with 95% statistical significance for message match tests
- 30 days of data per landing page variation
- Form analytics (field drop-off rates) for form optimization

### Detection Logic (Pseudocode)

```python
def detect_page_speed_issues(landing_pages, crux_data):
    for lp in landing_pages:
        cwv = crux_data.get(lp.url)
        if not cwv:
            yield Alert("NO_CWV_DATA", url=lp.url,
                        details="No Core Web Vitals data — likely insufficient traffic or new page")
            continue

        issues = []
        if cwv.lcp > 4.0:
            issues.append(f"LCP {cwv.lcp:.1f}s (POOR — target ≤2.5s)")
        elif cwv.lcp > 2.5:
            issues.append(f"LCP {cwv.lcp:.1f}s (Needs Improvement — target ≤2.5s)")

        if cwv.inp > 500:
            issues.append(f"INP {cwv.inp}ms (POOR — target ≤200ms)")
        elif cwv.inp > 200:
            issues.append(f"INP {cwv.inp}ms (Needs Improvement)")

        if cwv.cls > 0.25:
            issues.append(f"CLS {cwv.cls:.2f} (POOR — target ≤0.1)")
        elif cwv.cls > 0.1:
            issues.append(f"CLS {cwv.cls:.2f} (Needs Improvement)")

        if issues:
            estimated_cpc_impact = estimate_qs_cpc_impact(cwv)
            yield Alert("CWV_ISSUES", url=lp.url, severity="high" if cwv.lcp > 4.0 else "medium",
                        details=f"{'; '.join(issues)}. "
                                f"Estimated CPC premium: +{estimated_cpc_impact:.0%}")


def detect_mobile_conversion_gap(account):
    desktop = get_metrics(account, device='DESKTOP', days=30)
    mobile = get_metrics(account, device='MOBILE', days=30)

    if mobile.conversions == 0 or desktop.conversions == 0:
        return None

    gap = 1 - (mobile.conversion_rate / desktop.conversion_rate)

    if gap > 0.50:
        return Alert("SEVERE_MOBILE_GAP", severity="high",
                     details=f"Mobile CVR {mobile.conversion_rate:.2%} vs Desktop "
                             f"{desktop.conversion_rate:.2%} — {gap:.0%} gap. "
                             f"Mobile gets {mobile.click_share:.0%} of clicks but "
                             f"only {mobile.conversion_share:.0%} of conversions. "
                             f"Prioritize mobile checkout/form optimization.")
    elif gap > 0.35:
        return Alert("MOBILE_GAP", severity="medium",
                     details=f"Mobile CVR gap of {gap:.0%} — within typical range (35-42%) "
                             f"but optimization opportunity exists")

    return None


def detect_message_match_issues(campaign, landing_pages):
    for ad_group in campaign.ad_groups:
        ads = get_ads(ad_group)
        lp_url = ad_group.final_url

        for ad in ads:
            lp_headline = get_lp_headline(lp_url)
            ad_headlines = ad.headlines

            similarity = max(text_similarity(h, lp_headline) for h in ad_headlines)
            if similarity < 0.50:
                yield Alert("MESSAGE_MISMATCH",
                            ad_group=ad_group.name,
                            details=f"Low message match ({similarity:.0%}) between ad headlines "
                                    f"and landing page headline. Expected 2-3x CVR lift "
                                    f"with proper message matching.")


def detect_form_optimization(landing_page):
    form = get_form_fields(landing_page.url)
    if not form:
        return None

    field_count = len(form.fields)
    has_phone = any(f.type == 'phone' for f in form.fields)

    issues = []
    if field_count > 5:
        estimated_cvr_loss = (field_count - 3) * 0.08  # ~8% per extra field
        issues.append(f"{field_count} fields — each field above 3 reduces CVR by ~7-10%")

    if has_phone:
        issues.append("Phone number field present — typically reduces CVR by ~20%")

    if issues:
        return Alert("FORM_FRICTION", url=landing_page.url,
                     details="; ".join(issues))

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Landing page = PDP (product detail page). Speed and mobile optimization critical — mobile is 65% of traffic. Focus on checkout friction, not form fields. |
| **Lead Gen** | Form optimization is the primary lever. Name + Email + one qualifier = ~25% CVR. Phone field reduces CVR by ~20%. |
| **B2B / High-value** | More form fields justified (company, role, budget) because lead qualification matters. Accept lower CVR for higher lead quality. |
| **Mobile-first** | LCP target should be ≤2.0s (tightened in March 2026). Thumb-friendly CTAs, auto-fill enabled, minimal scrolling. |
| **Local services** | Click-to-call replaces form for mobile. Track phone calls as conversions. |

### Sources

- Core Web Vitals: vjseomarketing.com, mjmads.com, webbrandify.com (LCP/INP/CLS thresholds 2026)
- Nostra AI: nostra.ai (speed → CVR correlation, +21% CVR case study)
- Moz: moz.com/blog/message-match-conversion-rates (+212.74% case study)
- HawkSEM: hawksem.com/blog/landing-page-optimization/ (form optimization, message match)
- Landingi: QS and landing page experience correlation
- LevnTech/PxlPeak: PPC landing page optimization guides

---

## Domain 10: Seasonality & External Events

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| YoY seasonal deviation | >20% from prior year same period | Flag as anomaly — investigate external cause vs account issue |
| Day-of-week CPA variance | B2B: weekdays = $186 CPL vs weekends = $281 CPL (+51%) | Apply day-of-week bid adjustments |
| Day-of-week performance split | B2B: Mon-Thu = 74.4% of leads; Fri-Sun = 25.6% | Budget pacing should weight weekdays |
| Seasonality adjustment window | 1–7 days recommended duration | For short-term events (sales, holidays); not ongoing trends |
| Conversion rate change signal | >30% CR change in seasonality adjustment | Google's recommended usage threshold for seasonality adjustments |
| Post-event normalization | 3–7 days after event ends | Smart Bidding takes this long to return to baseline |
| Week-over-week comparison validity | Must use equal-length contiguous periods | Same day-of-week alignment required |
| Reporting lag adjustment | 2–14 days depending on conversion delay | Don't evaluate incomplete data windows |

**Seasonal baseline methodology:**
1. Collect 2+ years of weekly data per vertical
2. Compute 4-week rolling averages to smooth noise
3. Calculate YoY index (current week / same week prior year)
4. Flag deviations >20% from expected seasonal index
5. Cross-reference with Google Trends API for category-level validation
6. Separate account-specific issues from market-level shifts

### Minimum Data Requirements

- 2+ years of historical data for reliable seasonal baselines
- Weekly granularity minimum (daily preferred)
- Day-of-week segmentation for 90+ days
- Google Trends data for category-level context
- Industry benchmark data for vertical comparison
- At least 5 accounts per vertical for benchmark validity

### Detection Logic (Pseudocode)

```python
def detect_seasonal_anomaly(account, metric='conversions'):
    current_week = get_weekly_metric(account, metric, weeks=1)
    prior_year_same_week = get_weekly_metric(account, metric, weeks=1, year_offset=-1)
    rolling_avg_4w = get_rolling_avg(account, metric, weeks=4)

    yoy_change = (current_week - prior_year_same_week) / prior_year_same_week
    vs_rolling = (current_week - rolling_avg_4w) / rolling_avg_4w

    if abs(yoy_change) > 0.20 and abs(vs_rolling) > 0.15:
        # Check if this is market-level or account-specific
        category_trend = get_google_trends(account.category, weeks=1)
        category_yoy = category_trend.yoy_change

        if abs(category_yoy) > 0.15:
            return Alert("MARKET_LEVEL_SHIFT",
                         details=f"Account {metric} {yoy_change:+.0%} YoY, "
                                 f"but category trend is {category_yoy:+.0%} — "
                                 f"this is a market shift, not an account issue")
        else:
            return Alert("ACCOUNT_ANOMALY", severity="high",
                         details=f"Account {metric} {yoy_change:+.0%} YoY while "
                                 f"category is stable ({category_yoy:+.0%}). "
                                 f"Investigate account-specific causes.")

    return None


def detect_day_of_week_inefficiency(account, lookback_days=90):
    daily_metrics = get_daily_metrics(account, days=lookback_days)

    by_dow = defaultdict(list)
    for day in daily_metrics:
        by_dow[day.day_of_week].append(day)

    avg_cpa_by_dow = {dow: mean([d.cpa for d in days]) for dow, days in by_dow.items()}
    overall_avg_cpa = mean([d.cpa for d in daily_metrics])

    inefficient_days = []
    for dow, avg_cpa in avg_cpa_by_dow.items():
        if avg_cpa > overall_avg_cpa * 1.30:
            inefficient_days.append((dow, avg_cpa))

    if inefficient_days:
        return Alert("DAY_OF_WEEK_INEFFICIENCY",
                     details=f"CPA on {', '.join([d[0] for d in inefficient_days])} is "
                             f">30% above average. Apply negative bid adjustments or "
                             f"use ad scheduling to reduce exposure.")

    return None


def build_seasonal_baseline(account, years=2):
    """Build a seasonal index for YoY comparison."""
    weekly_data = get_weekly_metrics(account, years=years)

    seasonal_index = {}
    for week_num in range(1, 53):
        week_values = [w.conversions for w in weekly_data if w.iso_week == week_num]
        if len(week_values) >= 2:
            seasonal_index[week_num] = {
                'mean': mean(week_values),
                'std': stdev(week_values) if len(week_values) > 1 else 0,
                'upper_bound': mean(week_values) + 2 * stdev(week_values),
                'lower_bound': max(0, mean(week_values) - 2 * stdev(week_values))
            }

    return seasonal_index


def apply_seasonality_adjustment(campaign, event_start, event_end, expected_cr_change):
    """Create Google Ads seasonality adjustment for short-term events."""
    if (event_end - event_start).days > 14:
        return Alert("ADJUSTMENT_TOO_LONG",
                     details="Seasonality adjustments should be ≤14 days. "
                             "For longer trends, adjust targets instead.")

    if abs(expected_cr_change) < 0.30:
        return Alert("ADJUSTMENT_TOO_SMALL",
                     details=f"Expected CR change of {expected_cr_change:.0%} is below "
                             f"30% threshold. Smart Bidding handles small fluctuations automatically.")

    return SeasonalityAdjustment(
        campaign=campaign,
        start_date=event_start,
        end_date=event_end,
        conversion_rate_modifier=expected_cr_change
    )
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Strong seasonal patterns: Q4 (Black Friday/Cyber Monday), post-holiday lulls. Use 3+ years of data for baseline. Seasonality adjustments critical for flash sales. |
| **B2B / Lead Gen** | Day-of-week patterns dominant over seasonal (Mon–Thu vs Fri–Sun). Budget should weight weekdays 70–75%. |
| **Travel / Hospitality** | Highly seasonal with long booking windows. Search behavior leads conversion by 4–12 weeks. |
| **Education** | Enrollment cycles (Aug–Sep, Jan) create sharp peaks. Ramp paid spend 6–8 weeks before enrollment deadlines. |
| **Local services** | Weather-dependent verticals (HVAC, landscaping) show micro-seasonal patterns. Cross-reference with weather API. |

### Sources

- WordStream: wordstream.com/blog/seasonality-adjustments (seasonality adjustment guide)
- Google Ads API: Bidding seasonality adjustment documentation
- Blobr: blobr.io (weekly fluctuation diagnosis framework)
- Growth Spree: day-of-week performance analysis (B2B CPL data)
- YeezyPay: seasonality adjustments explained

---

## Domain 11: Cross-Channel Attribution

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| GA4 attribution lookback window | 30 days (default) | Extend to 90 days for B2B / long sales cycles |
| Assisted conversion ratio | >0.5 assists per last-click conversion for a channel | Channel provides significant assist value — don't cut based on last-click alone |
| MER (Marketing Efficiency Ratio) | Total Revenue / Total Ad Spend | Blended metric across all channels; track weekly trend rather than absolute number |
| MER healthy range (ecommerce) | 3.0–8.0x depending on margin | Below 3.0x with 50%+ margins = investigate channel allocation |
| Incrementality test minimum spend | $5,000 (reduced from $100K+ in 2025) | Google's new lower threshold makes testing accessible to more accounts |
| Conversion Lift test duration | 2–4 weeks | Shorter tests may not capture delayed conversions |
| Platform attribution vs actual | Google Ads over-reports by 15–40% on average | Cross-reference with GA4 DDA and third-party (Northbeam/Triple Whale) |
| Display/YouTube assist-to-convert ratio | 3–10 assists per last-click conversion | Upper funnel channels provide disproportionate assist value |
| Search assist-to-convert ratio | 0.5–1.5 assists per last-click conversion | Both assists and converts directly |

**Incrementality estimation framework:**
1. **Geo-split testing**: Split regions into treatment (ads on) and holdout (ads off); measure total conversion difference
2. **User-level testing**: Meta/Google Conversion Lift randomizes users into ad-exposed and holdout groups
3. **Matched market testing**: Compare similar DMAs with different ad exposure levels
4. **Pre/post analysis**: Controlled on/off periods with statistical significance requirements

### Minimum Data Requirements

- GA4 with enhanced conversions enabled
- 30+ days of cross-channel data for attribution modeling
- $5,000+ spend for Google Ads Conversion Lift testing
- 1,000+ conversions per channel per month for reliable attribution
- Server-side tracking (GTM server-side) for accurate cross-device matching
- At least 2 attribution models compared (DDA + last-click minimum)

### Detection Logic (Pseudocode)

```python
def detect_attribution_discrepancy(account, ga4_data):
    for campaign in account.campaigns:
        google_conversions = campaign.conversions_last_30d
        ga4_conversions = ga4_data.get_conversions(
            source='google', campaign=campaign.name, days=30, model='data_driven')

        discrepancy = abs(google_conversions - ga4_conversions) / google_conversions

        if discrepancy > 0.30:
            yield Alert("ATTRIBUTION_DISCREPANCY", severity="high",
                        campaign=campaign.name,
                        details=f"Google reports {google_conversions} vs GA4 DDA "
                                f"{ga4_conversions} — {discrepancy:.0%} gap. "
                                f"Review conversion tracking setup and attribution window.")


def calculate_mer(account, revenue_data, all_channel_spend):
    total_revenue = revenue_data.total_revenue_last_30d
    total_spend = sum(ch.spend_last_30d for ch in all_channel_spend)
    mer = total_revenue / total_spend if total_spend > 0 else 0

    mer_trend = calculate_weekly_trend(account, 'mer', weeks=8)

    if mer_trend.slope < -0.05:
        return Alert("MER_DECLINING",
                     details=f"MER at {mer:.1f}x and declining {mer_trend.slope:.2f}/week. "
                             f"Overall marketing efficiency deteriorating.")

    return {'mer': mer, 'trend': mer_trend}


def identify_assist_heavy_channels(ga4_data):
    channels = ga4_data.get_channel_attribution(days=30)
    for channel in channels:
        assist_ratio = channel.assisted_conversions / max(channel.last_click_conversions, 1)

        if assist_ratio > 3.0 and channel.last_click_conversions < 10:
            yield Alert("UNDERVALUED_CHANNEL", channel=channel.name,
                        details=f"Assist ratio {assist_ratio:.1f}x — this channel provides "
                                f"{channel.assisted_conversions} assists but only "
                                f"{channel.last_click_conversions} last-click conversions. "
                                f"Cutting spend based on last-click would be a mistake.")


def design_incrementality_test(account, campaign_type):
    """Recommend incrementality test design based on account profile."""
    monthly_spend = account.monthly_spend

    if monthly_spend < 5000:
        return TestDesign("PRE_POST",
                          method="Time-based on/off test",
                          duration_weeks=4,
                          notes="Insufficient budget for geo-split. "
                                "Run 2 weeks on, 2 weeks off, compare total outcomes.")

    elif monthly_spend < 50000:
        return TestDesign("GEO_SPLIT",
                          method="2-region geo test",
                          duration_weeks=4,
                          notes="Split into 2 comparable regions. "
                                "Treatment=ads on, Control=ads off. "
                                "Measure total conversion difference.")

    else:
        return TestDesign("CONVERSION_LIFT",
                          method="Google Conversion Lift",
                          duration_weeks=3,
                          notes="Use Google's randomized user-level test. "
                                "$5K minimum spend threshold. "
                                "Measures Incremental Conversions, Lift %, iROAS.")


def estimate_channel_incrementality(account, channel_data):
    """Estimate incrementality score per campaign type based on heuristics."""
    incrementality_benchmarks = {
        'BRAND_SEARCH': 0.50,       # 50% incremental (rest would come organically)
        'NONBRAND_SEARCH': 0.85,    # 85% incremental
        'PERFORMANCE_MAX': 0.60,    # 60% incremental (brand leakage reduces this)
        'SHOPPING': 0.75,           # 75% incremental
        'YOUTUBE': 0.40,            # 40% incremental (awareness, hard to attribute)
        'DISPLAY': 0.20,            # 20% incremental (mostly remarketing/view-through)
        'DEMAND_GEN': 0.50,         # 50% incremental
    }

    for campaign in account.campaigns:
        benchmark = incrementality_benchmarks.get(campaign.type, 0.50)
        estimated_incremental_conv = campaign.conversions_last_30d * benchmark

        yield {
            'campaign': campaign.name,
            'type': campaign.type,
            'reported_conversions': campaign.conversions_last_30d,
            'estimated_incremental': estimated_incremental_conv,
            'incrementality_score': benchmark,
            'note': 'Estimate only — run Conversion Lift test to validate'
        }
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | MER is primary north star metric. GA4 DDA is default model. Third-party attribution (Northbeam/Triple Whale) recommended for $50K+/month accounts. |
| **Lead Gen** | Offline conversion import essential — form fill ≠ revenue. Attribution should weight by lead quality/close rate, not raw conversion count. |
| **B2B / long cycle** | Extend GA4 lookback to 90 days. First-touch attribution more relevant for upper-funnel channels. CRM integration required for closed-won attribution. |
| **Multi-channel** | Never optimize a single channel in isolation. MER trend is the true signal. Channel-level ROAS is directional, not definitive. |
| **DTC** | Post-purchase surveys ("How did you hear about us?") complement click-based attribution for brand awareness channels. |

### Sources

- GA4 Attribution: Google Analytics 4 attribution documentation
- Google Ads Conversion Lift: support.google.com/google-ads/answer/12003020
- Google Incrementality: support.google.com/google-ads/answer/16719772
- Northbeam: northbeam.io/blog/introducing-incrementality
- Triple Whale: triplewhale.com/blog/incrementality-testing-methods
- Adnan Agic: adnanagic.com/blog/incrementality-testing-google-ads/

---

## Domain 12: Creative & Ad Copy Patterns

### Quantified Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Ad Strength vs actual performance | "Average" Ad Strength = best CPA ($12.43, 12.65% CVR) | Do NOT optimize for Excellent Ad Strength — it correlates with worse performance |
| "Excellent" Ad Strength actual CPA | $28.68 (worst) with 4.97% CVR | Counterintuitive — high Ad Strength ≠ high performance |
| "Poor" Ad Strength ROAS | 327.65% (best ROAS) | Ad Strength reflects structural completeness, not predictive quality |
| Optimal headline length | <20 characters | Delivers lowest CPA per Optmyzr study of ~20K accounts |
| Optimal description length | 61–70 characters | Sweet spot for description performance |
| Text case | Sentence case > Title Case | Sentence case outperforms title case |
| Pinning strategy | Partial pinning > Full pinning > No pinning | Pin 1–2 key headlines to position 1; leave rest flexible |
| Extension coverage (sitelinks) | Minimum 4 sitelinks per campaign (8–10 recommended) | +10–15% CTR typical; +20–50% on branded searches |
| Extension coverage (callouts) | 6–8 callouts per campaign | Google selects 2–4 per auction |
| Overall extension CTR lift | +10–25% vs ads without extensions | Extensions contribute to Ad Rank |
| Top 10% creative vs average | 3.2x better results | Creative quality is the dominant performance lever |
| Bottom 10% creative | 0.2x of average (5x worse) | Immediately pause poor performers |
| RSA asset rating "LOW" threshold | >30% of assets rated LOW | Replace LOW-rated assets with new variations |

**Creative testing framework:**
1. Test hooks/headlines first (highest impact)
2. Then visual style and CTAs
3. Then descriptions and micro-optimizations
4. Isolate one variable at a time
5. Minimum 1,000 impressions per variant before declaring winner
6. Run for at least 2 weeks to account for day-of-week variation

**Extension coverage scoring:**

| Extension Type | Weight | Present | Missing |
|---------------|--------|---------|---------|
| Sitelinks (4+) | 30% | ✓ | -30% CTR potential |
| Callouts (4+) | 20% | ✓ | -20% ad real estate |
| Structured Snippets (1+) | 15% | ✓ | Missed category signaling |
| Call Extension | 10% | ✓ | Missed mobile conversions |
| Image Extension | 15% | ✓ | -10-15% engagement potential |
| Price Extension | 10% | ✓ | Missed pre-qualification |
| **Total Score** | **100%** | **Calculate % of total** | **Below 60% = action needed** |

### Minimum Data Requirements

- 1,000+ impressions per ad variant for reliable testing
- 14 days minimum test duration
- 100+ conversions per ad group for CPA-based optimization
- Headline-level click and conversion data (available in Google Ads 2026)
- Asset performance labels require 5,000+ impressions to stabilize
- At least 3 active RSA variants per ad group for testing

### Detection Logic (Pseudocode)

```python
def detect_rsa_asset_performance(campaign):
    for ad_group in campaign.ad_groups:
        ads = get_rsas(ad_group)
        for ad in ads:
            low_assets = [a for a in ad.assets if a.performance_label == 'LOW']
            total_assets = len(ad.assets)

            if len(low_assets) / total_assets > 0.30:
                yield Alert("HIGH_LOW_ASSET_RATE",
                            ad_group=ad_group.name,
                            details=f"{len(low_assets)}/{total_assets} assets rated LOW. "
                                    f"Replace with new variations. Focus on headlines first.")

            # Check headline length optimization
            long_headlines = [h for h in ad.headlines if len(h.text) > 20]
            if len(long_headlines) > len(ad.headlines) * 0.50:
                yield Alert("LONG_HEADLINES",
                            details=f"{len(long_headlines)} headlines >20 chars — "
                                    f"shorter headlines (<20 chars) deliver lower CPA")


def detect_ad_strength_misoptimization(campaign):
    """Flag when teams are optimizing for Ad Strength instead of actual performance."""
    for ad_group in campaign.ad_groups:
        ads = get_rsas(ad_group)
        if len(ads) < 2:
            continue

        excellent_ads = [a for a in ads if a.ad_strength == 'EXCELLENT']
        average_ads = [a for a in ads if a.ad_strength == 'AVERAGE']

        for exc_ad in excellent_ads:
            for avg_ad in average_ads:
                if avg_ad.cpa < exc_ad.cpa * 0.80:
                    yield Alert("AD_STRENGTH_PARADOX",
                                ad_group=ad_group.name,
                                details=f"'Average' Ad Strength outperforming 'Excellent' by "
                                        f"{(1 - avg_ad.cpa/exc_ad.cpa):.0%} on CPA. "
                                        f"Ad Strength ≠ performance. Optimize by CPA/ROAS, "
                                        f"not Ad Strength rating.")


def score_extension_coverage(campaign):
    extensions = get_extensions(campaign)

    scoring = {
        'sitelinks': {'weight': 0.30, 'present': len(extensions.sitelinks) >= 4},
        'callouts': {'weight': 0.20, 'present': len(extensions.callouts) >= 4},
        'structured_snippets': {'weight': 0.15, 'present': len(extensions.structured_snippets) >= 1},
        'call': {'weight': 0.10, 'present': extensions.call_extension is not None},
        'image': {'weight': 0.15, 'present': len(extensions.images) >= 1},
        'price': {'weight': 0.10, 'present': extensions.price_extension is not None},
    }

    total_score = sum(s['weight'] for s in scoring.values() if s['present'])
    missing = [name for name, s in scoring.items() if not s['present']]

    if total_score < 0.60:
        return Alert("LOW_EXTENSION_COVERAGE", severity="high",
                     campaign=campaign.name,
                     score=total_score,
                     details=f"Extension coverage score: {total_score:.0%}. "
                             f"Missing: {', '.join(missing)}. "
                             f"Extensions provide +10-25% CTR lift.")

    return {'score': total_score, 'missing': missing}


def detect_creative_testing_velocity(account):
    ad_groups = get_ad_groups(account)
    under_tested = []

    for ag in ad_groups:
        ads = get_rsas(ag)
        if len(ads) < 2:
            under_tested.append(ag.name)

        recent_ads = [a for a in ads if a.created_days_ago < 90]
        if len(recent_ads) == 0 and len(ads) > 0:
            under_tested.append(f"{ag.name} (stale — no new ads in 90 days)")

    if len(under_tested) > len(ad_groups) * 0.30:
        return Alert("LOW_CREATIVE_TESTING",
                     details=f"{len(under_tested)}/{len(ad_groups)} ad groups under-tested or stale. "
                             f"Run at least 2 RSA variants per ad group and refresh every 90 days.")

    return None
```

### Segment Variations

| Segment | Variation |
|---------|-----------|
| **Ecommerce** | Price and promotion messaging dominant. Use price extensions heavily. Specificity wins: "$49.99" outperforms "Affordable Prices". |
| **Lead Gen** | Emotional + urgency messaging converts best. Test "limited time" vs "free consultation" vs "expert team". Callout extensions for trust signals (years in business, certifications). |
| **B2B / SaaS** | Rational messaging with specific proof points: "Used by 10,000+ companies" > "Trusted solution". Sitelinks to case studies, pricing, demo pages. |
| **Local services** | Location-specific copy wins. Call extensions critical for mobile. Structured snippets for service areas. |
| **Competitive markets** | Competitor comparison angles need testing carefully — can backfire. Focus on differentiation rather than direct comparison. |

### Sources

- Optmyzr: optmyzr.com/blog/google-rsa-performance-study/ (~20K account RSA study, April 2026)
- Search Engine Land: searchengineland.com (RSA headline performance data)
- Google Ads Help: RSA and extension documentation
- Benly.ai: benly.ai/learn/google-ads/google-ads-assets-extensions (19 extension types 2026)
- Clarigital: clarigital.com/codex/sem/google-ads/ad-extensions/ (extension deep dive)

---

## Appendix: Cross-Domain Detection Priority Matrix

For a 500-account engine, prioritize detection implementation in this order based on impact × frequency:

| Priority | Domain | Rationale |
|----------|--------|-----------|
| 1 | Bidding Strategy (6) | Wrong strategy = everything downstream fails. Quick to detect, high impact. |
| 2 | Campaign Structure (7) | Fragmentation undermines Smart Bidding. Structural fix enables all other optimizations. |
| 3 | Branded Search (1) | Brand/non-brand contamination is the #1 audit finding (VIDEN: 150+ accounts). |
| 4 | Quality Score / Non-Brand (2) | QS below 5 on high-spend keywords = quantifiable waste. |
| 5 | Landing Page / CVR (9) | Core Web Vitals directly impact QS and conversion; measurable via API. |
| 6 | PMax Patterns (3) | Fastest-growing campaign type; channel distribution opacity requires proactive monitoring. |
| 7 | Shopping / Feed (5) | Title optimization has documented +18–95% conversion lifts. High ROI per engineering hour. |
| 8 | Creative / Ad Copy (12) | RSA asset performance data newly available; Ad Strength paradox is widely misunderstood. |
| 9 | Seasonality (10) | Prevents false alarms; distinguishes environment from account issues. |
| 10 | SEO × Paid (8) | AI Overviews reshaping SERP economics — critical for 2026 but requires GSC integration. |
| 11 | YouTube / Video (4) | Growing channel but lower detection urgency vs Search/Shopping fundamentals. |
| 12 | Cross-Channel Attribution (11) | Important but requires extensive data infrastructure; build last as a validation layer. |
