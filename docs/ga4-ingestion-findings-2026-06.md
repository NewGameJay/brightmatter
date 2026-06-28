# GA4 Ingestion, Detectors & Cross-Platform Upgrades: Findings & Review

*Date: 2026-06-28. Branch: `main`. Built from the `research/ga4/` bundle. All numbers
computed against live GA4 (info@hawkemedia.com) + the existing Google Ads panel.
GA4 metadata + report data only; no writes to any ad platform.*

This is the build phase after GA4 Phase 1 (discovery). It ingests GA4 landing-page
engagement, runs GA4-native detectors, and — the payoff — joins GA4 evidence to
Google Ads signals to upgrade their confidence tiers.

---

## Run parameters

| Parameter | Value |
|---|---|
| GA4 properties visible (info@hawkemedia.com) | **232** |
| Properties matching our Ads panel | **15** (12 usable after quality gate) |
| GA4 landing-page rows ingested | **82,032** (landing_page × device × date, 28d) |
| Distinct pages / accounts | 14,739 / 12 |
| Campaign final URLs ingested | **12,263** across **3,170 campaigns** / 15 accounts |
| GA4-native detector signals | **38** across 6 accounts |
| Ads signals upgraded LIKELY→CONFIRMED | **25** |

---

## Changelog

| Commit | What |
|---|---|
| `0c49549` | Land `research/ga4/` bundle (API/scope rules, 5 detection domains, 6 causal chains, benchmarks, experts, signal map) |
| `ef2b8ea` | GA4 Tier 1.1 ingestion — landing-page engagement (`ga4_landing_pages`) + implementation-quality gate (`ga4_property_health`) |
| `b1a32ad` | GA4 detectors (Domains 1–2) — engagement drop, duration collapse, mobile gap, mobile bounce regression |
| `cd5f9ba` | Campaign final-URL ingestion (`campaign_final_urls`) + cross-platform join (`cross_platform_links`) → 25 confidence upgrades |

New tables: `ga4_landing_pages`, `ga4_property_health`, `page_speed`,
`ga4_funnel_events`, `campaign_final_urls`, `cross_platform_links`. New modules:
`ingestion/ga4.py`, `analysis/ga4_detectors.py`, `analysis/ga4_crossref.py`. New
scripts: `ga4_oauth.py`, `ga4_ingest.py`, `ga4_detectors_run.py`,
`ga4_ingest_final_urls.py`, `ga4_crossref_run.py`.

---

## What worked

### The implementation-quality gate caught real garbage
Per the expert frameworks (Ahava/Seiden/Fedorovicius: most GA4 setups are broken),
every property is checked before its data is trusted. It **correctly skipped 2 of 15**
properties: Teak Warehouse (97.7% overall engagement = a key-event firing on every
pageview, which would have produced meaningless 97% engagement everywhere) and
Sundance Spa (no sessions in window). Without this gate, Teak Warehouse would have
silently polluted every downstream signal.

### GA4-native detectors produce CONFIRMED signals
38 signals across 6 accounts — engagement drops, duration collapses, mobile gaps,
mobile bounce regressions — all CONFIRMED tier (GA4 directly measures engagement),
each carrying an honest "what we can't tell you" = *why* (the cause), deferred to
the page-audit layer.

### The cross-platform join delivered the actual prize
This is what the whole GA4 effort was for: **25 Google Ads signals moved from LIKELY
to CONFIRMED** with a named page and a GA4 number written into the signal:
- 17 **landing-page chain** (cvr_drop/cvr_change/cpa_spike/cpa_change + GA4 weak or
  falling engagement on the campaign's page) — e.g. *cvr_change on
  `/hot-tub-sale-pricing` confirmed by 34% engagement*; multiple homepage signals
  confirmed by 20% engagement.
- 8 **mobile-UX chain** (device_mobile_drag + GA4 mobile engagement gap) — e.g.
  mobile 31% vs desktop 76%.

"CVR dropped, can't rule out the landing page" became "CVR dropped **and** GA4
confirms this page runs 34% engagement." That is the confidence upgrade the
confidence framework was built to receive.

---

## What we learned

### CrUX is unnecessary — squirrelscan + Firecrawl are a better fit
The page-speed/QS branch (research Domain 4 / Chain 5) was going to need CrUX. The
team already has **squirrelscan** (the `audit-website` skill, `squirrel` CLI v0.0.52)
— a full 150-rule site auditor (perf, mobile, technical, security) — plus Firecrawl
for raw page fetch. Together they cover not just page speed but the deeper "*why* is
this page broken" layer the research said needed visual inspection. CrUX dropped with
no loss.

### GA4 access is broad but barely overlaps our panel (carried from Phase 1)
232 properties visible, but only 15 are our Ads accounts. GA4 here is a 15-account
capability (12 usable), not a panel-wide layer — and the 25 upgrades all come from
that small set.

---

## What we expected but didn't get

1. **A high URL-join hit rate — got 10%.** The biggest finding of the build. We
   expected campaign final-URL paths to match GA4 landing pages cleanly. They don't,
   and it is **not a normalization bug**: high-traffic GA4 properties (e.g. italki:
   2.5M sessions on `(not set)`, 80K on `/`, 65K on `(other)`) collapse the
   `landingPage` dimension into GA4's `(not set)`/`(other)` cardinality-overflow
   buckets — a documented GA4 API limit. Those properties are simply unjoinable at
   the page grain. The join works well on the ~5 accounts with intact page
   cardinality (50–100% hit); it's the big accounts that drag the average to 10%.
   The fix to extend coverage is known but unbuilt: query GA4 *filtered* to each
   campaign's known paths (`dimensionFilter landingPage IN (...)`), which sidesteps
   the overflow and returns exact per-page data even on huge properties.

2. **Panel-wide page-level GA4 — not available on big accounts either.** The same
   cardinality collapse means the GA4-native detectors also can't see specific pages
   on the highest-traffic properties. Page-level GA4 is a small/mid-traffic-property
   capability until BigQuery export or filtered queries are added.

3. **More than 25 upgrades.** 151 Ads signals on matched accounts → only 100 had a
   joinable page → 25 cleared a corroboration bar. Honest, but modest — and
   concentrated on a few weak pages (homepages, `/hot-tub-sale-pricing`) that many
   campaigns share.

---

## Errors & fixes (for the record)

| Issue | Fix |
|---|---|
| Both OAuth tokens died mid-build (`invalid_grant`) | Root cause: the OAuth app is in **"Testing"** status → refresh tokens expire after **7 days**. Re-authed both (`ga4_oauth.py`, `refresh_oauth.py`). **Durable fix still pending: publish the consent screen to "In production."** |
| `runReport` metricValues parse crash (`string indices must be integers`) | Was double-indexing `["value"]` after already extracting the values list. Fixed. |
| `ad_group_ad` final-URL query would explode on Shopping (one row per product, 80K+) | Filtered to ad-bearing channels (Search/Display/Demand Gen/Video) + `asset_group` for PMax; Shopping correctly excluded (no campaign final_url exists — it's feed-based). Same lesson as the Phase-4.75 ad-strength hang. |
| GA4 `(not set)` null-bucket leaking in as a fake "page" | Excluded `(not set)`/`(other)`/`''` from detectors and the join. |
| Property with 97.7% engagement would inflate every signal | Implementation-quality gate skips it before ingestion. |

---

## Lock-in scorecard

| Criterion | Status |
|---|---|
| GA4 access operational | ✅ info@hawkemedia.com, 232 properties (token re-authed) |
| Landing-page engagement ingested | ✅ 82,032 rows / 12 accounts |
| Implementation-quality gate | ✅ skipped 2 misconfigured/empty properties |
| GA4-native detectors live | ✅ 38 CONFIRMED signals (Domains 1–2) |
| Campaign final URLs for the join | ✅ 12,263 / 3,170 campaigns |
| Cross-platform confidence upgrades | ✅ 25 signals LIKELY→CONFIRMED (chains 1 & 2) |
| Join hit rate honest + explained | ✅ 10%, cause = GA4 cardinality overflow (documented) |
| Page-speed branch | ➖ CrUX dropped; squirrelscan/Firecrawl to supply the "why" (next) |
| Funnel + source-split detectors | ⏸️ deferred (Tier 2 — need funnel-event + source ingestion) |
| Durable token fix | ❌ pending — publish OAuth consent screen |

---

## Net read & next steps

The GA4 layer does what it was meant to: it turns vague "can't rule out the landing
page" Google Ads signals into **confirmed, page-specific diagnoses** — 25 of them
this build. The honest ceiling is coverage, not mechanism: only 15 of 223 accounts
overlap this GA4 login, and the precise page join collapses on the highest-traffic
properties (a GA4 cardinality limit, not our code). Where the data is clean, the
chain works exactly as designed.

**Recommended next:**
- **squirrelscan the confirmed-broken pages** (`/hot-tub-sale-pricing` @34%,
  20%-engagement homepages) → the *why* (perf/mobile/technical defects), closing the
  loop from "this page is the problem" to "here's what to fix."
- **Filtered GA4 queries** (`landingPage IN campaign-paths`) to recover the big
  high-traffic accounts the cardinality overflow currently blocks.
- **Publish the OAuth consent screen** so both tokens stop expiring every 7 days.
- GA4 Tier 2 (ecommerce funnel events; source split for the paid-bounce / traffic-
  quality detectors) when the 15-account base justifies it.

> Reproduce: `ga4_ingest.py` → `ga4_detectors_run.py` → `ga4_ingest_final_urls.py`
> → `ga4_crossref_run.py`. Populated tables live in the gitignored DuckDB.
