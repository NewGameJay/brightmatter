# GA4 Phase 1 — Discovery, Research & Signal Mapping: Findings

*Run date: 2026-06-20. Branch: `main`. Discovery grounded in existing BrightMatter
data + a live GA4 auth probe via `scripts/ga4_phase1_discovery.py`. No GA4 data
pulled (per spec — that's GA4 Phase 2).*

This phase answers: which accounts have usable GA4, what GA4 signals would measurably
improve BrightMatter, and is it worth ingesting — ranked by expected impact and
grounded in real signal volumes, not narrative.

---

## 1.0 Discovery

### Auth assessment — the operational blocker, found honestly

A live probe of both tokens in this environment:

| Credential | Scope | GA4 Admin API |
|---|---|---|
| `GOOGLE_ADS_REFRESH_TOKEN` | `adwords` only | **403 ACCESS_TOKEN_SCOPE_INSUFFICIENT** |
| `GA4_REFRESH_TOKEN` (ai@marketerhire.com, `analytics.readonly`) | — | **can't mint — `unauthorized_client`** |

**GA4 access is provisioned-in-principle but not operational here.** Someone set up
a GA4 OAuth token (`analytics.readonly` for `ai@marketerhire.com`) and one
`GA4_PROPERTY_ID` is known — but the matching OAuth **client_id/client_secret for
that GA4 token are not in this repo's `.env`**, so it can't be exchanged for an
access token. The Google Ads token is `adwords`-scoped only and is correctly refused
by the GA4 API.

**The single blocker for live GA4 discovery/ingestion:** provision the GA4 OAuth
client credentials (the `ai@marketerhire.com` client_id + secret that issued
`GA4_REFRESH_TOKEN`), **or** grant a service account GA4 *Viewer* access per property.
Until then, live property enumeration (data depth, CWV detection, custom-event
inventory) cannot run. This is the documented coverage gap the spec asks for.

### Discovery mapping — from data already in hand

What we *can* establish without GA4 API access, across the **223 active accounts**:

| Mapping dimension | Count | Use |
|---|---|---|
| Accounts with a website URL | **193 / 223 (87%)** | URL-match to GA4 property |
| Accounts importing GA4-style goals | **20** | confirmed GA4↔Ads linkage (strongest match signal) |
| Accounts with any ecommerce funnel event | 21 | candidate funnel accounts |
| Accounts with **full** funnel instrumented (add_to_cart **+** begin_checkout **+** purchase) | **12** | the only accounts where Signal 3 is fully usable |

The 20 imported-goal accounts are the highest-confidence GA4 matches (they already
push GA4 conversions into Ads, proving a live link). The 193 URL'd accounts are
URL-match candidates once API access exists. The live columns (`ga4_property_id`,
`data_months`, `cwv_enabled`, `custom_events_count`) are **pending_access**.

---

## 1.1 Research — what GA4 signals matter (and what it doesn't give us)

GA4 is event-based, not session-based. The relevant consequences for BrightMatter:

- **Engagement rate replaces bounce rate** — sessions >10s OR 2+ pages OR a key
  event. This is the metric that maps to landing-page quality, and it's per
  landing-page × device × day via the Data API.
- **Scope mismatch is a real query hazard** — session-scoped (landing page) vs
  event-scoped (conversions) vs user-scoped dimensions can't be freely combined;
  joins must respect scope or return blanks. Phase 2 ingestion must query each scope
  separately.
- **Core Web Vitals are NOT in GA4 by default** — they require a GTM + web-vitals JS
  setup most properties lack. **CrUX API (Chrome UX Report) is the reliable page-speed
  source** — public, URL-keyed, **no GA4 auth and no client instrumentation needed.**
- **No authoritative GA4 engagement benchmarks exist** (the UA-era ones use a
  different definition) — so GA4 signals are useful as *within-account temporal
  deltas* (engagement dropped 15% the day CVR dropped), not as absolute "good/bad"
  thresholds. This fits BrightMatter's episode model exactly.

What GA4 does **not** give us, that the roadmap must not assume: real-time page speed
(use CrUX), deterministic cross-device tracking (it's modeled), full conversion paths
(consent-limited), or causal page→CVR proof (still needs BrightMatter's temporal
correlation).

---

## 1.2 Signal mapping — ranked, grounded in REAL BrightMatter signal volumes

Each GA4 signal is scored against the actual count of BrightMatter signals it could
upgrade (from the live DB), not a guess.

| Rank | GA4 signal | BrightMatter gap it fills | Addressable volume (measured) | Effort | Blocker |
|---|---|---|---|---|---|
| **1** | Landing-page **engagement rate** (page×device×day) | CVR/CPA signals stuck at LIKELY → could reach CONFIRMED when engagement moves with CVR | **1,130 signals** (729 CVR + 401 CPA), 100% currently capped at LIKELY, **0 CONFIRMED** | Low (1 API call) | GA4 access |
| **2** | **Mobile vs desktop** engagement gap | `device_mobile_drag` — explains *why* mobile CVR is low | **385 signals**, currently untiered | Low (add device dim) | GA4 access |
| **3** | Ecommerce **funnel drop-off** | pinpoints *where* CVR breaks (cart vs checkout) | **only 12 accounts** fully instrumented | Medium | GA4 access + 12-acct ceiling |
| **4** | Page speed via **CrUX** | QS landing-page-experience penalties | up to 193 URL'd accounts | Low | **none — public API, unblocked** |
| 5 | Session duration / scroll | secondary "why engagement is what it is" | diagnostic only | Low | GA4 access |
| 6 | Session-source attribution | cross-channel future (Meta↔Google) | low now, high later | Medium | GA4 access |

**The headline:** GA4's #1 signal (engagement rate) targets **1,130 CVR/CPA signals
that are currently capped at LIKELY and cannot reach CONFIRMED** — the single largest
documented confidence gap in the system. #2 adds 385 device signals. Together ~1,500
signals (of the current ~2,300 total) are GA4-addressable. That is a large, real,
measured prize.

**The critical caveat (from Phase 6.75):** GA4 engagement would upgrade
*diagnostic confidence* (is the landing page the cause?), but Phase 6.75 showed CVR
and conversions are *intrinsically* WEAK to predict (47–55pp per-metric MAE). So GA4's
value is **confidence-tier upgrades and better act-vs-wait diagnosis, not
necessarily tighter magnitude prediction.** Those are two different value claims;
GA4 Phase 3 must measure both separately and not conflate them.

---

## Measurement framework (how GA4 Phase 3 proves its worth)

Each signal's value is a measured delta against the Phase-5 baseline:
1. **Confidence upgrades** — how many of the 1,130 CVR/CPA signals move LIKELY →
   CONFIRMED when GA4 engagement corroborates? Target: >30% to justify the build.
2. **Template MAE** — does adding GA4 landing-page-engagement state as a template
   conditioning variable lower per-metric MAE? (Honest expectation: small, given the
   6.75 intrinsic-noise finding.)
3. **Recommendation quality** — does act-vs-wait produce different/better calls with
   GA4 context? Measured by the same recommendation-accuracy metric as Phase 5.

If all three are minimal, GA4 doesn't justify the engineering. If engagement rate
upgrades ≥30% of CVR signals, Phase 2 is warranted.

---

## Honest go / no-go

**Conditional GO — for Signals 1, 2, and 4, once the GA4 credential is provisioned.**

- **Signals 1 + 2 (engagement rate + device gap)** are the prize: ~1,500 addressable
  signals, low effort, need only GA4 read access. **Top-3 for Phase 2.**
- **Signal 4 (CrUX page speed) is unblocked today** — public API, 193 URLs, no GA4
  auth. It can proceed *in parallel* regardless of the credential gap, and is the
  pragmatic first GA4-adjacent ingestion. **Recommended immediate, low-risk start.**
- **Signal 3 (ecommerce funnel) is deferred** — only 12 accounts are fully
  instrumented; the reach doesn't justify the medium effort yet.
- **Signals 5, 6 deferred** — diagnostic / cross-channel-future, low immediate value.

**The one hard blocker:** GA4 API access is not operational in this environment.
Nothing in GA4 Phase 2 (except CrUX) can proceed until the `ai@marketerhire.com` GA4
OAuth client_id/secret are added to `.env`, or a service account is granted per-
property Viewer access. **This is the gating action item — a credentials/permissions
task, not an engineering one.**

---

## Lock-in scorecard (GA4 Phase 1)

| Criterion | Status |
|---|---|
| GA4 property → Ads account mapping | ⚠️ partial from existing data (20 linked, 193 URL-match candidates); **live property IDs pending GA4 access** |
| Data inventory per property | ❌ blocked — needs GA4 API access (documented) |
| Auth status documented | ✅ adwords-only token 403s; GA4 token client creds absent; 1 property known |
| Signal ranking with expected impact | ✅ grounded in real volumes (1,130 CVR/CPA, 385 device, 12 ecom) |
| Measurement framework defined | ✅ confidence upgrades / MAE / rec-quality |
| Top 3 signals for Phase 2 | ✅ engagement rate, device gap, CrUX page-speed |
| Honest "is it worth it" assessment | ✅ conditional GO (1+2+4); blocker is credentials, not value |

5 of 7 fully met; the 2 partials are blocked on GA4 API credentials — an external
provisioning step, documented as the gating action item.

---

## Net read

The *value case* for GA4 is real and quantified: engagement rate alone targets 1,130
CVR/CPA signals that today can't exceed LIKELY confidence. But two honest constraints
shape the plan: **(1)** live GA4 access isn't operational here (a missing OAuth client
credential — the single gating blocker), and **(2)** per Phase 6.75, GA4 will likely
lift *diagnostic confidence* more than *magnitude precision*, so GA4 Phase 3 must
measure both and claim only what it earns. The pragmatic path: **start CrUX page-speed
now (unblocked), and provision the GA4 credential to unlock Signals 1+2** — the high-
value core — for Phase 2 ingestion.

> Reproduce: `python scripts/ga4_phase1_discovery.py` (auth probe + mapping + signal
> volumes). No GA4 data is pulled.
