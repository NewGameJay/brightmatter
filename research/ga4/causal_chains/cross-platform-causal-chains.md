# Cross-Platform Causal Chains: GA4 × Google Ads

*6 diagnostic patterns that only become visible when both data sources are combined. Each maps to a specific BrightMatter signal or template gap.*

---

## Chain 1: Landing Page Degradation → CVR Drop

**Cause (GA4):** Landing page engagement rate drops >15pp (page redesign, speed degradation, broken element, pop-up added, content change)

**Mechanism (GA4):** Users arrive via Google Ads click but leave within 10 seconds without engaging. Bounce rate spikes on paid traffic specifically.

**Effect (Google Ads):** CVR drops across campaigns pointing to that landing page. CPA spikes. ROAS declines.

**Detection signature:**
- GA4: engagement_rate for landing_page X dropped >15pp vs 14-day baseline
- Google Ads: CVR on campaigns with final_url matching X dropped simultaneously
- Temporal alignment: GA4 shift precedes or coincides with Google Ads shift (same day or 1-2 day lag)

**Confidence upgrade:** CVR drop from SUGGESTIVE ("can't rule out landing page") → LIKELY ("engagement dropped on the same page at the same time") → CONFIRMED if the drop is isolated to that specific page while other pages are stable

**What this can't prove:** WHY the page degraded. Was it a redesign? A speed issue? A content change? A broken form? GA4 shows the effect on user behavior but not the technical cause. CrUX can add page speed. Visual inspection or site monitoring tools identify the rest.

**BrightMatter action:** Flag episodes where GA4 engagement dropped simultaneously with Google Ads CVR. Tag as `landing_page_confirmed`. These episodes get higher confidence in template extraction because the causal mechanism is visible.

---

## Chain 2: Mobile UX Failure → Device Performance Gap

**Cause (GA4):** Mobile engagement rate is 35% while desktop is 72% on the same landing page. Mobile session duration is 8 seconds vs desktop 90 seconds.

**Mechanism (GA4):** The landing page works on desktop but fails on mobile — slow load, broken layout, unreadable text, non-tappable buttons, intrusive pop-up.

**Effect (Google Ads):** Campaign-level CVR is low because 65% of traffic is mobile and mobile doesn't convert. Blended CPA is high. Smart Bidding optimizes against a mixed signal.

**Detection signature:**
- GA4: mobile bounce_rate > desktop bounce_rate + 25pp on the same landing page
- GA4: mobile engagement_rate < 40% while desktop > 60%
- Google Ads: device_mobile_drag signal already firing (Phase 4.75 detector)
- Cross-reference: the same landing page URL appears in both datasets

**Confidence upgrade:** device_mobile_drag from LIKELY ("mobile CVR is lower but we don't know why") → CONFIRMED ("mobile engagement rate is 35% on this specific page — the mobile experience is broken")

**What this can't prove:** What specifically about the mobile experience is broken. GA4 shows the behavioral result. CrUX can add mobile LCP/CLS/INP. But "the form is too small to tap" requires visual inspection.

**BrightMatter action:** When device_mobile_drag fires AND GA4 confirms mobile engagement is significantly worse, the recommendation changes from "investigate mobile performance" to "fix mobile UX on [specific landing page URL] — mobile engagement is [X]% vs desktop [Y]%."

---

## Chain 3: Ecommerce Funnel Breakpoint → ROAS Decline

**Cause (GA4):** Drop-off at a specific funnel step — view_item→add_to_cart, OR add_to_cart→begin_checkout, OR begin_checkout→purchase.

**Mechanism (GA4):** Each step represents a different conversion barrier:
- view_item→add_to_cart drop: product page issue (pricing, imagery, reviews, out of stock)
- add_to_cart→begin_checkout drop: cart UX issue (unclear pricing, no guest checkout, forced account creation)
- begin_checkout→purchase drop: checkout friction (payment failures, unexpected shipping costs, slow loading, trust issues)

**Effect (Google Ads):** ROAS drops. Conversion volume drops. CPA spikes. But Google Ads can't see WHERE in the funnel the issue is.

**Detection signature:**
- GA4: one funnel step's conversion rate dropped >20% while upstream steps are stable
- Google Ads: ROAS or CVR dropped on ecommerce campaigns pointing to the affected pages
- Cross-reference: funnel events on the same pages receiving Google Ads traffic

**Confidence upgrade:** ROAS decline from SUGGESTIVE → CONFIRMED with specific funnel step identified

**What this can't prove:** What caused the specific funnel step to break. A checkout drop could be a payment gateway issue, a shipping cost change, a coupon code error, or a page load regression. GA4 identifies the step; the fix requires investigating that step specifically.

**BrightMatter action:** When ecommerce ROAS drops AND GA4 identifies a specific funnel breakpoint, the recommendation includes: "Investigate [specific funnel step]. Drop-off rate increased from [X]% to [Y]%. The issue is between [step A] and [step B], not in the Google Ads campaign."

---

## Chain 4: Ad-to-Page Message Mismatch

**Cause (Google Ads):** New RSA (ad creative) went live. The headline promises something the landing page doesn't deliver.

**Mechanism (GA4):** Paid traffic bounce rate spikes while organic traffic bounce rate is stable on the same page. Users click the ad expecting X, arrive at the page, don't see X, leave.

**Effect (Google Ads):** CTR may be good (the ad is compelling). But CVR drops and CPA spikes (the page doesn't deliver on the ad's promise).

**Detection signature:**
- Google Ads: creative change (ad_creative episode) occurred
- GA4: bounce_rate for sessions where sessionSource = 'google' AND sessionMedium = 'cpc' spiked
- GA4: bounce_rate for organic sessions on the SAME page is stable
- Temporal: GA4 bounce spike starts on or after the creative change date

**Confidence upgrade:** "Creative change degraded CPA" from LIKELY → CONFIRMED ("the new ad is driving clicks that don't match the page content — paid bounce rate spiked 25pp while organic is stable")

**What this can't prove:** Whether fixing the ad or fixing the page is the right response. Both are valid: change the ad to match the page, or change the page to match the ad.

**BrightMatter action:** When a creative change episode shows CPA degradation AND GA4 confirms paid-only bounce spike, the recommendation specifies: "The new ad copy may not match the landing page content. Paid bounce rate spiked from [X]% to [Y]% while organic is stable at [Z]%. Either update the landing page to match the ad's message, or revert to the previous ad copy."

---

## Chain 5: Page Speed Degradation → QS Penalty → CPC Increase

**Cause (CrUX):** LCP increased from 2.1s to 4.5s on a key landing page (hosting issue, unoptimized images, third-party scripts).

**Mechanism (Google Ads):** Google's Quality Score landing page experience component degrades from "Average" to "Below Average."

**Effect (Google Ads):** CPC increases ~20-40% for keywords pointing to that page. At the same budget, fewer clicks, fewer conversions. CPA rises.

**Detection signature:**
- CrUX: LCP for a landing page URL shifted from "Good" (≤2.5s) to "Poor" (>4s)
- Google Ads: Quality Score dropped on keywords associated with that URL
- Google Ads: CPC increased for those keywords without auction/competitive changes

**Confidence upgrade:** QS landing page experience penalty from "Below Average" rating only (no explanation) → CONFIRMED with specific metric ("LCP is 4.5 seconds — well into 'Poor' range. This directly explains the QS penalty.")

**What this can't prove:** Why LCP degraded. Could be: hosting provider issue, new third-party script, unoptimized hero image, excessive DOM size. CrUX identifies the metric; the fix requires front-end investigation.

**BrightMatter action:** When low QS signal fires AND CrUX shows Poor speed on the same URL, the recommendation includes: "Landing page LCP is [X]s ([category]). This is causing a Quality Score penalty that increases CPC by an estimated [Y]%. Fix: optimize page speed on [URL]. Target LCP ≤2.5s."

---

## Chain 6: Attribution Model Discrepancy

**Cause:** Google Ads and GA4 use different attribution models.

**Mechanism:** Google Ads credits conversions within its own ecosystem (data-driven within Google Ads). GA4 credits conversions across ALL traffic sources (data-driven across email, organic, social, paid search, etc.). Same user, same conversion, different credit assigned.

**Effect:** Google Ads says campaign X drove 50 conversions. GA4 says campaign X drove 35. The 15-conversion gap is credit that GA4 assigned to other channels in the path.

**Detection signature:**
- Google Ads: campaign reports X conversions
- GA4: sessions from that campaign had Y key events (Y < X)
- Gap percentage: (X - Y) / X

**What this reveals:**
- If the gap is large (>30%): the campaign is an "assister" not a "closer." It drives awareness that converts through other channels. Last-click evaluation undervalues it. Data-driven evaluation gives it appropriate credit.
- If the gap is small (<10%): the campaign is a genuine last-touch converter. Both attribution models agree.
- If GA4 shows MORE conversions: rare, but possible if GA4's model assigns credit to Google Ads touchpoints that the Ads model discounts.

**BrightMatter action:** For the 15 cross-referenced accounts, compute the attribution gap per campaign. Annotate templates: "This campaign's template accuracy may be affected by a [X]% attribution discrepancy — GA4 attributes [Y]% fewer conversions to this campaign than Google Ads does." Templates built on high-gap campaigns should have wider confidence intervals.

---

## Summary: Which Chains Are Testable Now

| Chain | Requires | Coverage | Priority |
|-------|----------|----------|----------|
| 1. Landing page degradation | GA4 engagement data | 193 accounts | HIGH |
| 2. Mobile UX failure | GA4 device-segmented engagement | 193 accounts | HIGH |
| 3. Funnel breakpoint | GA4 ecommerce events | ~80-100 accounts (ecommerce only) | MEDIUM |
| 4. Message mismatch | GA4 source-segmented bounce | 15 cross-referenced accounts | MEDIUM |
| 5. Page speed → QS | CrUX + Google Ads QS | 193 accounts (CrUX) | MEDIUM |
| 6. Attribution discrepancy | GA4 + Google Ads conversion comparison | 15 cross-referenced accounts | LOW (future) |

Chains 1, 2, and 5 are testable across the full 193-account panel. Chains 3 is limited to ecommerce accounts with funnel tracking. Chains 4 and 6 require the 15 cross-referenced accounts (GA4 source attribution needs the Google Ads link to identify which sessions came from which campaigns).
