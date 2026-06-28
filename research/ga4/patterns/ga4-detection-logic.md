# GA4 Pattern Detection Logic

*5 detection domains for GA4 as a standalone platform. Each detector follows the same BrightMatter pattern: detect → harness → confidence tier → threshold from YAML.*

---

## Domain 1: Landing Page Quality

Detects degradation in landing page performance that directly affects Google Ads conversion rates.

### Detector 1.1: Engagement Rate Drop
- **Signal:** Landing page engagement rate dropped >15pp vs 14-day baseline
- **Severity:** Warning (>15pp drop), Critical (>25pp drop)
- **Threshold source:** GA4 research benchmarks — cross-industry median is 52.6%. A 15pp drop from any baseline is significant.
- **Confidence tier:** CONFIRMED — engagement rate is directly measured by GA4.
- **What we can't tell you:** WHY engagement dropped. Could be: page redesign, speed issue, broken element, pop-up, content change, seasonal shift.
- **Check next:** CrUX for page speed change. Visual inspection of the page. Recent deploy/CMS changes.
- **Harness tests:** (1) Is the drop isolated to this page or site-wide? (site-wide = hosting/CMS issue, not page-specific). (2) Is the drop isolated to one traffic source? (paid-only = ad-to-page mismatch, all sources = genuine page issue). (3) Is the page volume sufficient? (<50 sessions/week = noisy, may be random).

### Detector 1.2: Paid Traffic Bounce Spike
- **Signal:** Bounce rate on sessions from google/cpc spiked >20pp while organic bounce is stable on the same page
- **Severity:** Warning
- **Confidence tier:** CONFIRMED — source-segmented bounce is directly measured
- **What we can't tell you:** Whether the ad copy or the page is "wrong." The mismatch goes both ways.
- **Cross-platform link:** When this fires simultaneously with a Google Ads creative change episode, it's Chain 4 (message mismatch). Upgrade from SUGGESTIVE to CONFIRMED.

### Detector 1.3: Session Duration Collapse
- **Signal:** Average session duration on a landing page dropped >50% vs 14-day baseline
- **Severity:** Info (>50% drop), Warning (>75% drop)
- **Confidence tier:** LIKELY — duration is measured but affected by changes in user mix, not just page quality
- **What we can't tell you:** Whether users are leaving because the page is bad or because they found what they needed faster.

---

## Domain 2: Device Experience

Detects mobile-specific UX failures that explain device performance gaps in Google Ads.

### Detector 2.1: Mobile Engagement Gap
- **Signal:** Mobile engagement rate < desktop engagement rate − 25pp on the same landing page with >100 sessions per device
- **Severity:** Warning
- **Confidence tier:** CONFIRMED — device-segmented engagement is directly measured
- **Threshold source:** The structural gap is ~12pp (Digital Applied 2026). Beyond 25pp, the gap indicates a page-specific mobile problem, not just the structural device difference.
- **Cross-platform link:** Upgrades the Google Ads device_mobile_drag signal from LIKELY to CONFIRMED when both fire on the same page.

### Detector 2.2: Mobile-Only Bounce Regression
- **Signal:** Mobile bounce rate increased >15pp while desktop bounce is stable on the same page
- **Severity:** Warning
- **Confidence tier:** CONFIRMED — the desktop stability serves as the control
- **What we can't tell you:** What broke on mobile. Could be: layout shift, unreadable font, non-tappable button, slow load on mobile networks.

---

## Domain 3: Ecommerce Funnel Health (ecommerce accounts only)

Detects WHERE in the purchase funnel conversion breaks.

### Detector 3.1: Funnel Step Drop-Off
- **Signal:** One funnel step's conversion rate dropped >20% vs 14-day baseline while adjacent steps are stable
- **Scope:** view_item → add_to_cart → begin_checkout → purchase
- **Severity:** Warning per step, Critical if purchase step drops
- **Confidence tier:** CONFIRMED if the drop is isolated to one step (other steps stable = the issue is at that specific step)
- **What we can't tell you:** What caused the step to break. Product page issue vs pricing vs UX vs technical error.
- **Harness tests:** (1) Is the drop on all products or one specific product? (2) Is the drop on all devices or mobile-only? (3) Did the drop coincide with a website deploy or product change?

### Detector 3.2: Overall Funnel Compression
- **Signal:** ALL funnel steps dropped proportionally (view → cart → checkout → purchase all down ~15%)
- **Severity:** Warning
- **Confidence tier:** LIKELY — proportional drops suggest traffic quality issue (wrong audience), not funnel UX
- **Cross-platform link:** Check Google Ads: did targeting change? Did a new campaign launch? Did broad match expand to less-relevant queries?

---

## Domain 4: Page Speed (CrUX)

Detects page load performance issues that affect both UX and Google Ads Quality Score.

### Detector 4.1: Core Web Vitals Failure
- **Signal:** LCP > 4.0s OR CLS > 0.25 OR INP > 500ms on a landing page receiving Google Ads traffic
- **Severity:** Warning (Needs Improvement range), Critical (Poor range)
- **Confidence tier:** CONFIRMED — CrUX is field data from real Chrome users
- **Cross-platform link:** If Google Ads QS landing page experience is "Below Average" AND CrUX shows Poor metrics, the diagnosis is CONFIRMED: page speed is causing the QS penalty.
- **Coverage:** All 193 URL'd accounts via public CrUX API

### Detector 4.2: Speed Regression
- **Signal:** Any Core Web Vital shifted from Good → Needs Improvement or Needs Improvement → Poor since the last CrUX check
- **Severity:** Warning
- **Note:** CrUX data updates on a 28-day rolling basis, not daily. This detector runs monthly, not daily.

---

## Domain 5: Traffic Source Quality

Detects quality differences between traffic sources that explain Google Ads performance anomalies.

### Detector 5.1: Paid vs Organic Quality Gap
- **Signal:** Paid search sessions have engagement rate >20pp lower than organic sessions on the same site
- **Severity:** Info
- **Confidence tier:** LIKELY — some gap is expected (paid reaches broader audience), but >20pp suggests targeting or message mismatch
- **What we can't tell you:** Whether the paid targeting is wrong or the organic audience is just inherently better-qualified
- **Cross-platform link:** If this fires while Google Ads campaigns are using broad match expansion, the search terms quality may be the issue

### Detector 5.2: Source Engagement Anomaly
- **Signal:** One traffic source's engagement rate dropped >15pp while other sources are stable
- **Severity:** Info
- **Confidence tier:** CONFIRMED — source-segmented engagement is directly measured
- **What this means:** Something changed about that specific traffic source — campaign change, audience shift, or platform algorithm update

---

## Implementation Notes

### All GA4 detectors follow the BrightMatter pattern:
1. Query GA4 Data API for the relevant metrics
2. Compare against baseline (14-day rolling average or vertical benchmark)
3. Apply threshold from `config/ga4_thresholds.yaml`
4. Produce signal with confidence tier and "what we can't tell you"
5. Harness challenges the finding against adjacent data
6. Cross-reference with Google Ads signals where applicable

### Data anchor:
GA4 detectors use `MAX(date) FROM ga4_landing_pages` as the anchor, same pattern as Google Ads detectors. GA4 data typically lags 24-48 hours from the Data API.

### Minimum volume thresholds:
- Landing page signals: minimum 50 sessions/week on the page
- Device split signals: minimum 100 sessions per device per week
- Funnel signals: minimum 50 events per step per week
- Speed signals: CrUX requires sufficient Chrome traffic (typically >1,000 page loads in 28 days)

Below these thresholds, signals are suppressed (too noisy to be meaningful).
