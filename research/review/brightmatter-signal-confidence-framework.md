# BrightMatter Signal Confidence Framework

*For every signal BrightMatter produces: what can we prove from Google Ads data alone, what do we believe but can't prove, and what does the user need to verify externally.*

---

## Principles

1. **Never present a theory as a fact.** If we can't confirm it from the data we have, say so.
2. **Disproven is valuable.** A signal that says "this ISN'T the problem" saves the user from wasting time on the wrong fix.
3. **Confidence has three tiers**, not two. It's not just "we know" or "we don't know" — there's a critical middle tier of "the data strongly suggests this, but here's what could be wrong and here's how to check."
4. **The experienced marketer is the last mile.** BrightMatter's job is to surface what's happening, explain what it likely means, be honest about what it can't see, and tell the marketer exactly what to check. Their 20 years of context is the final filter.
5. **Vertical context is not optional.** A skincare ecommerce brand and a personal injury law firm have completely different benchmarks, campaign structures, conversion types, and seasonal patterns. Every signal must be evaluated against the right baseline.

---

## Confidence Tiers

### Tier 1: CONFIRMED — Provable from Google Ads data alone

These are structural facts, not interpretations. The data directly shows the condition. No external validation needed to confirm the signal — only to decide what to do about it.

**What qualifies:** The signal is a direct measurement or a logical certainty from the data. If the data says it, it's true.

### Tier 2: LIKELY — Strong evidence, but alternative explanations exist

The pattern is real and the most probable interpretation is clear, but Google Ads data alone can't rule out all other causes. We state what we believe, why we believe it, and what could make us wrong.

**What qualifies:** Statistical patterns, performance shifts, correlations across accounts. The signal is real — the *cause* has alternatives we can't eliminate.

### Tier 3: SUGGESTIVE — Something is happening, but we can't determine why

We see a data anomaly worth investigating, but Google Ads data alone doesn't give us enough to even rank the likely causes. We flag it, describe what we see, and hand it to the marketer with a specific checklist of what to investigate.

**What qualifies:** Performance changes that could have multiple equally-plausible causes, patterns that need context we don't have.

---

## Detector Confidence Map

### CONFIRMED — What we can prove from Google Ads data

---

**Tracking Break Detection**
- **What we confirm:** Conversions dropped >80% across all campaigns in the same account on the same day while clicks remained stable.
- **Why this is provable:** If clicks are flowing and conversions aren't recording, measurement is broken. This is arithmetic, not interpretation.
- **What we can't tell you:** Whether it's a GTM tag issue, a website change, a payment gateway break, or a consent mode misconfiguration. The fix requires investigating the tracking implementation.
- **Recommendation frame:** "Tracking appears broken in this account as of [date]. Conversions dropped from [X] to [Y] while clicks stayed at [Z]. Do not make campaign changes until tracking is verified. Check: GTM tags firing? Conversion page URLs changed? Consent mode configured correctly?"

---

**Auto-Applied Changes Detection**
- **What we confirm:** Google made [X] changes to this account without human approval. The Change History API records who made each change — this is not an inference, it's a direct log.
- **Why this is provable:** The actor field in change_event explicitly distinguishes human from auto-applied from Google Ads system changes.
- **What we can't tell you:** Whether the auto-applied changes helped or hurt. We can correlate with performance via episodes, but correlation isn't causation — performance may have changed for other reasons at the same time.
- **Recommendation frame:** "[X] auto-applied changes detected in the last 30 days, including [types]. [Y]% of all changes in this account are auto-applied, not human. Review the change log and opt out of recommendation types that don't align with campaign strategy. Episode data shows [improved/degraded/neutral] performance after these changes, but other factors may be involved."

---

**Conversion Action Misconfiguration**
- **What we confirm:** This account has [page views / micro-conversions / duplicate actions] set as primary conversion actions. Smart Bidding optimizes for whatever you tell it to — if the primary action is wrong, bidding is optimizing for the wrong thing.
- **Why this is provable:** The conversion_action resource directly reports action type, category, primary_for_goal status, and counting type. This is configuration, not interpretation.
- **What we can't tell you:** Whether the configuration was intentional. Some accounts deliberately use micro-conversions as primary when macro-conversion volume is too low for Smart Bidding.
- **Recommendation frame:** "This account has [X] primary conversion actions including [page_view / begin_checkout / etc.]. Smart Bidding is optimizing for all of these equally. If [action] isn't a true business outcome, consider moving it to secondary. This directly affects what Google's algorithm bids for."

---

**Bidding Anti-Patterns**
- **What we confirm:** This campaign uses broad match keywords with manual CPC (or Maximize Clicks). Broad match requires Smart Bidding's auction-time signals to work effectively — without them, broad match expands to low-intent queries with no bid adjustment.
- **Why this is provable:** The keyword match type and bidding strategy are directly reported. The interaction between them is documented by Google and confirmed by every Tier 1 expert (Vallaeys, Geddes, ALM Corp).
- **What we can't tell you:** Whether the broad match keywords are actually wasting spend. Confirming that requires search terms report analysis (which we can do) and conversion quality assessment (which may need CRM data).
- **Recommendation frame:** "Campaign '[name]' has [X] broad match keywords running with [manual CPC / Maximize Clicks]. Broad match needs Smart Bidding signals to avoid irrelevant queries. Either switch to a conversion-based bidding strategy (tCPA, tROAS, Max Conversions) or tighten match types to exact/phrase."

---

**Campaign Structure Issues**
- **What we confirm:** This account has [X campaigns with <30 conversions/month each]. Smart Bidding needs minimum conversion volume to learn. Over-segmented accounts fragment this signal.
- **Why this is provable:** Campaign count, conversion volume, and bidding strategy are directly measured. The 30 conversions/month threshold is documented by Google and validated by smec across 1,000+ campaigns.
- **What we can't tell you:** Whether consolidation would actually improve performance. Sometimes segmented campaigns serve different audiences or geographies that genuinely need separate strategies.
- **Recommendation frame:** "This account has [X] campaigns averaging [Y] conversions/month each. Smart Bidding needs 30-50 conversions/month per campaign to optimize effectively. Consider consolidating campaigns that target similar audiences or products. The exception is campaigns serving genuinely different geographies, languages, or business lines."

---

**Missing Brand/Non-Brand Separation**
- **What we confirm:** This account has no campaign with "brand" in its name and runs keywords that include the company's brand terms mixed with non-brand terms in the same campaigns.
- **Why this is provable:** Campaign names and keyword text are directly visible. Brand token matching against the account name confirms whether brand terms exist in non-brand-labeled campaigns.
- **What we can't tell you:** Whether separation would improve performance. For low-spend accounts, separating may fragment an already-thin conversion signal.
- **Recommendation frame:** "Brand and non-brand keywords appear to be mixed in the same campaigns. This makes it impossible to measure brand vs. non-brand performance independently, and prevents applying different bidding strategies to each. Consider separating into dedicated brand and non-brand campaigns if monthly conversion volume supports it (30+ per campaign)."

---

**Quality Score Components**
- **What we confirm:** Keyword '[text]' has a Quality Score of [X]/10. Expected CTR: [rating]. Ad Relevance: [rating]. Landing Page Experience: [rating]. This keyword is paying an estimated [Y]% CPC premium compared to a QS 7+ keyword.
- **Why this is provable:** Quality Score components are directly reported by Google at the keyword level. The CPC premium relationship is documented in Google's own materials and confirmed by Geddes and TwoSquares research.
- **What we can't tell you:** Exactly how much more you're paying in absolute dollars (QS affects auction dynamics, not just CPC), or what specifically about the landing page needs to change. Landing Page Experience is a rating, not a diagnostic.
- **Recommendation frame:** "Keywords with QS below 5 and significant spend are costing you materially more per click. Focus on the component rated 'Below Average' first. For Landing Page Experience: check page speed, mobile usability, and content relevance to the keyword. For Expected CTR: test new ad copy with higher keyword relevance. For Ad Relevance: ensure ad copy directly addresses the keyword's intent."

---

**Budget Constraint (when validated)**
- **What we confirm:** Campaign '[name]' is losing [X]% of eligible impressions due to budget constraints. It captured [Y]% of available impression share over the last [Z] days.
- **Why this is provable:** Search impression share and budget-lost impression share are directly measured by Google's auction system.
- **What we can't tell you:** Whether the incremental impressions would convert profitably. Budget-lost IS tells you there's demand you're not capturing — it doesn't tell you whether capturing it would be worth the cost. That depends on marginal CPA, which requires incrementality testing or at minimum a period of budget increase to observe.
- **Recommendation frame:** "This campaign consistently leaves [X]% of available impressions uncaptured due to budget. Current ROAS is [Y]x on existing spend. If marginal returns hold, increasing budget could capture [estimated additional conversions]. However, diminishing returns mean each additional dollar typically costs more than the last. Consider a controlled 20% budget increase for 2 weeks to measure marginal CPA before committing."

---

### LIKELY — Strong evidence, alternative explanations exist

---

**CPA Spike**
- **What we see:** Campaign '[name]' CPA increased from $[X] to $[Y] over the last 7 days — a [Z]x increase over the 30-day baseline.
- **What we've ruled out:** Not a tracking break (conversions are recording). Not low-volume noise (baseline has [N] conversions). Not an auto-applied change artifact (change history shows [human/no changes]).
- **What we believe:** The campaign's cost efficiency has genuinely degraded.
- **What we can't rule out:** Seasonal demand contraction (fewer high-intent searchers), competitor entry driving up CPCs (Auction Insights would show this but isn't pulled at this granularity yet), landing page degradation (page speed, broken elements), or cross-channel effects (awareness spending on other channels decreased, reducing warm traffic to Google).
- **What to check:** "Look at Auction Insights for this campaign — are new competitors appearing or existing ones gaining share? Check if the landing page was changed or if page speed degraded. Compare search volume trends for core keywords in Google Trends. If none of those explain it, the campaign may need creative refresh or keyword refinement."

---

**CVR Drop**
- **What we see:** Conversion rate for campaign '[name]' dropped from [X]% to [Y]% over the last 7 days — a [Z]% decline from baseline.
- **What we've ruled out:** Not a tracking break. Not low-volume noise. Click volume is stable (the traffic is coming, it's just not converting).
- **What we believe:** Something changed in the conversion path — either the traffic quality shifted or the conversion experience degraded.
- **What we can't rule out:** Landing page changes (design, speed, form fields, checkout flow), product/pricing changes (stockout, price increase, removed promotion), audience composition shift (broad match expanding to less-relevant queries), or seasonal intent shift (browsers vs. buyers).
- **What to check:** "Was the landing page or website changed? Check page load speed. For ecommerce: did product availability or pricing change? Pull the search terms report — are new, less-relevant queries entering through broad match? If it's a PMax campaign, check if the channel distribution shifted (more Display/YouTube, less Search)."

---

**Brand/Non-Brand ROAS Contamination**
- **What we see:** Blended account ROAS is [X]x, but brand campaigns deliver [Y]x while non-brand delivers [Z]x. The blended number masks that non-brand is [below break-even / significantly underperforming].
- **What we've validated:** Campaign labels match actual keyword composition (brand campaigns are genuinely brand-dominant). Conversion volume is sufficient on both sides for ROAS to be meaningful. No conversion tracking changes in the last 60 days that would distort the comparison. Brand ROAS is within plausible range (not inflated by value artifacts).
- **What we believe:** Non-brand campaigns are underperforming relative to brand, and the blended ROAS is masking this.
- **What we can't rule out:** Non-brand campaigns may be doing upper-funnel awareness work that converts through brand search later (cross-channel attribution). In that case, non-brand's "low ROAS" reflects its role as a pipeline builder, not its failure. This is fundamentally an attribution question that Google Ads last-click data can't answer.
- **What to check:** "Pull cross-channel attribution from GA4 or your attribution platform. Look at assisted conversion paths — does non-brand Search appear in the path before brand Search conversions? If non-brand is genuinely a pipeline builder, its ROAS should be evaluated on assisted value, not last-click. If it's not appearing in conversion paths, it may genuinely be underperforming."

---

**Cross-Account CPA Outlier**
- **What we see:** This account's CPA of $[X] is [Y] standard deviations above the peer group mean of $[Z].
- **What we've validated:** Comparison is against accounts in the same vertical and spend tier (once classification is complete). Volume is sufficient for CPA to be meaningful.
- **What we believe:** This account is paying significantly more per conversion than similar accounts.
- **What we can't rule out:** Different conversion types (one account tracks purchases, another tracks add-to-carts). Different geographic markets (NYC CPC vs. rural CPC). Different product price points (high-ticket items naturally have higher CPA but also higher value). Different business maturity (new accounts in learning phase vs. established accounts).
- **What to check:** "Compare conversion action types between this account and peers. Check geographic targeting — are you competing in a more expensive market? Look at conversion value, not just CPA — a $200 CPA with $2,000 AOV is better than a $50 CPA with $100 AOV. If none of those explain the gap, investigate account structure, bidding strategy, and creative quality."

---

### SUGGESTIVE — Something is happening, needs investigation

---

**PMax Channel Imbalance**
- **What we see:** PMax campaign '[name]' appears to be spending disproportionately on [Display/YouTube] rather than Search/Shopping (based on campaign-type-level metrics — PMax doesn't report channel breakdown directly in all cases).
- **Why this is uncertain:** PMax's channel allocation is intentionally opaque. Google provides limited channel-level reporting, and what's reported may not capture the full picture. A "Display-heavy" PMax might be doing effective prospecting that converts later through Search.
- **What to check:** "Review PMax placement reports if available. Check if the product feed is connected and healthy — PMax without a good feed defaults to non-Shopping placements. Look at the asset group structure — if search themes are missing or weak, PMax may be defaulting to Display. Consider running a PMax Uplift experiment (Google's built-in tool) to measure if PMax is adding incremental reach or just repackaging Display."

---

**Insufficient Conversions for Bidding Strategy**
- **What we see:** Campaign '[name]' uses [tCPA/tROAS/Max Conversions] but has only [X] conversions in the last 30 days. Smart Bidding needs 30-50 conversions/month to optimize effectively.
- **Why this is uncertain:** Some campaigns with <30 conversions still perform well if the conversion signal is clean and consistent. The 30/month number is a guideline, not a hard cutoff. Campaign age matters too — a new campaign in learning is expected to have low volume initially.
- **What to check:** "How old is this campaign? If it's <4 weeks old, low volume is expected during learning. If it's been running for months with <30 conversions, Smart Bidding doesn't have enough data to optimize — consider switching to Maximize Clicks temporarily to build volume, then transition back once you hit 30+/month. Alternatively, consolidate with similar campaigns to pool conversion signals."

---

## Account Classification: Non-Negotiable Foundation

Every signal's accuracy depends on comparing against the right baseline. These classifications must be set before signals become recommendations.

### Required Classifications

**Business Type** — Determines which metrics matter and what "good" looks like:
- Ecommerce: ROAS, AOV, CVR, conversion value are primary. CPA is secondary.
- Lead Gen: CPA, CPL, form submissions are primary. ROAS is often meaningless (no conversion value).
- Local Services: Calls, directions, appointments are primary. High brand % is normal, not contamination.
- SaaS: Trial signups, demo requests. Long sales cycles mean conversion lag distorts short-window analysis.
- B2B: Similar to lead gen but with longer cycles and higher ticket values.

**Vertical** — Determines benchmark ranges:
- A $50 CPA is excellent for legal, terrible for apparel ecommerce.
- A 2% CVR is normal for insurance lead gen, low for food/beverage ecommerce.
- 80% brand search share is expected for a dental practice, a red flag for a DTC brand.

**Spend Tier** — Determines volume expectations:
- <$5K/month: Low-volume patterns apply. Many detectors should soften thresholds or not fire.
- $5K-$25K: Standard thresholds. Enough data for most pattern detection.
- $25K-$100K: Full detector suite applies. Cross-campaign patterns become visible.
- $100K+: Advanced patterns (portfolio bidding optimization, marginal CPA analysis, channel allocation).

**Campaign Intent** — What each campaign is designed to do:
- Brand defense (protect brand terms from competitors)
- Non-brand acquisition (find new customers)
- Remarketing (re-engage past visitors)
- Awareness/prospecting (top of funnel, expected to have lower direct ROAS)
- Shopping/product feed (ecommerce product-level)
- Local (geographic targeting, calls/visits)

### How to Classify from Google Ads Data Alone

We have enough data to classify most accounts without external input:

- **Campaign names** reveal intent: "Brand", "NB", "Non-Brand", "Prospecting", "Retargeting", "Shopping", "PMax", geographic terms, product categories
- **Conversion action types** reveal business model: "Purchase" = ecommerce, "Lead Form Submit" / "Phone Call" = lead gen, "Book Appointment" = local services
- **Conversion values** reveal ticket size: if set, the average value tells you high-ticket vs. low-ticket
- **Geographic targeting** reveals scope: radius targeting = local, national = ecommerce/SaaS, multi-country = enterprise
- **Campaign type mix** reveals strategy: Shopping + PMax = likely ecommerce, Search-only = likely lead gen or local
- **Final URLs** reveal the business: the domain and page paths tell you what the company does

For the 454 accounts in the MCC, the classify_accounts() method should use these heuristics to assign business_type, vertical, and spend_tier. Where the heuristic is ambiguous, flag for manual review rather than guessing — "unknown" is better than wrong.

---

## What Google Ads Data CANNOT Tell Us (Documented Gaps)

These are the boundaries of what we can see. When we expand to GA4 or other sources, each of these becomes a filled gap, not a new feature.

1. **Landing page quality** — Google reports a QS component rating (Above/Average/Below Average) but not WHY. Page speed, mobile usability, content relevance, form UX — all invisible from Google Ads alone.

2. **Cross-channel attribution** — Google Ads takes credit for conversions using its own models. Whether a conversion was truly caused by the Google ad or was already in-flight from a Meta ad, email campaign, or organic visit is unknowable from Google Ads data.

3. **Customer quality** — A conversion is a conversion in Google Ads. Whether that lead turned into a $100K client or a no-show, whether that purchase was returned, whether that subscriber churned in week 1 — all invisible. CRM data fills this gap.

4. **Competitor strategy** — Auction Insights shows overlap and outranking rates but not what competitors are doing. Their ad copy, landing pages, offers, budget levels, and bidding strategies are not visible.

5. **Market conditions** — Search volume trends, economic shifts, seasonal patterns beyond what's visible in YoY data, news events affecting the vertical — all external context that affects performance but isn't in the Google Ads data.

6. **Website changes** — If the client changed their homepage, broke their checkout flow, added a pop-up, or migrated their CMS, we can see the performance impact but not the cause.

7. **True incrementality** — Would the conversion have happened without the ad? Google Ads can't answer this. Only holdout testing or geographic incrementality experiments can.

---

## How Signals Become Recommendations

A signal earns the right to become a recommendation only when:

1. **The harness validates it** — at least "supported" overall, zero false positives
2. **The confidence tier is documented** — the user knows whether it's CONFIRMED, LIKELY, or SUGGESTIVE
3. **The business context is applied** — vertical benchmarks, spend tier expectations, campaign intent
4. **The limitations are stated** — what we can't see and what to check
5. **The action is specific** — not "fix your CPA" but "check if the landing page changed; if not, review search terms for query expansion; if neither, consider tightening your tCPA target by 15%"
6. **The disproven alternatives are listed** — "We ruled out tracking break and low-volume noise. We could not rule out seasonal demand shift or competitor entry."

This is what separates BrightMatter from every other alerting tool. Most tools say "CPA is high." BrightMatter says "CPA spiked 4x. Here's what we know caused it, here's what we think caused it, here's what we can't determine, and here's exactly what to check next."
