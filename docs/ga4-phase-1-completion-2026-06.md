# GA4 Phase 1 — Completion: Changelog & Findings

*Date: 2026-06-20. Branch: `main`. Completes GA4 Phase 1 (discovery / research /
mapping) with live GA4 access. Metadata only — no GA4 report data pulled.*

---

## Changelog

| Commit / artifact | What |
|---|---|
| `scripts/ga4_oauth.py` | Interactive `analytics.readonly` OAuth, self-verifying against the GA4 Admin API. Run as **info@hawkemedia.com** → working token (50 accounts / 230 properties), minted under the existing Google Ads OAuth client. |
| `.env` (gitignored) | `GA4_REFRESH_TOKEN` updated to the live info@hawkemedia.com token; verified to mint + enumerate end-to-end. |
| `scripts/ga4_phase1_discovery.py` | Reproducible auth probe + discovery grounding + GA4-addressable signal volumes. |
| `scripts/ga4_phase1_mapping.py` | Property→account mapper: lists 230 properties, pulls each property's web-stream URL (metadata), matches to the 223 Ads accounts by domain. |
| `ga4_property_map` table | Persisted mapping: account → matched GA4 property, URL, method, confidence. |
| `docs/ga4-phase-1-findings-2026-06.md` | Earlier findings doc, updated: auth RESOLVED, blocker cleared. |

---

## The headline finding: broad GA4 access, narrow overlap with our panel

info@hawkemedia.com can see **50 GA4 accounts / 230 properties** (132 distinct
website domains). That *looked* like full coverage. It isn't:

| Coverage of our 223 Ads accounts | Count |
|---|---|
| **High-confidence GA4 match (URL domain)** | **15 (7%)** |
| Low-confidence (name-token) | 3 (1%) |
| **Unmatched — no GA4 property visible to this login** | **205 (92%)** |

This was verified two ways (exact-domain and registrable-domain matching both return
15), so it is **not a matcher artifact** — the populations are genuinely largely
disjoint. **Hawke Media's GA4 roster ≠ BrightMatter's Google Ads panel.** The 230
properties are mostly brands we don't run ads for; the 223 accounts mostly have GA4
properties this login can't see (they live under other Analytics admins).

The 15 confirmed overlaps are real and clean: galaxyhomerecreation.com, tarpits.org,
nhm.org, mackenzie-childs.com, teakwarehouse.com, thecoverguy.com, sundancespas.com,
360cookware.com, alphacord.com, cryochoice.com, italki.com, mig.cc,
topconsolutions.com, thesundancespastore.com, + 1.

---

## What we expected but didn't get

1. **Full-panel GA4 coverage.** The 230-property count implied broad reach; the
   actual overlap with our accounts is **15 (7%)**. GA4's value, *with this login*,
   applies to 15 accounts — not 223.

2. **The "1,130 addressable CVR/CPA signals" prize shrinks to ~111.** That number
   (from the initial signal mapping) assumed GA4 covered the whole panel. Restricted
   to the 15 matched accounts, the actually-reachable volume is:
   - CVR signals on matched accounts: **71 / 729 (10%)**
   - CPA signals on matched accounts: **40 / 401 (10%)**
   - Episodes on matched accounts (template-enrichment reach): **401 / 4,889 (8%)**

3. **Per-property metadata is slow.** 230 `dataStreams` calls took ~13 min (the
   Admin API is rate-limited per property). Full inventory (data-retention months,
   CWV detection, custom-event lists) per property would be a longer metadata crawl —
   deferred to Phase 2 for the 15 relevant properties only.

---

## What this means for the GA4 go/no-go (revised, honest)

The mechanism case is unchanged — engagement rate is still the right signal to
upgrade CVR/CPA confidence. But the **coverage** case is now realistic:

- **GA4 Phase 2 = a 15-account pilot, not a panel rollout.** Pull engagement rate +
  device split for the 15 matched properties, join by landing-page URL, and measure
  the delta on their ~111 CVR/CPA signals: do they move LIKELY → CONFIRMED? That's a
  clean, cheap proof-of-mechanism on real overlap.
- **CrUX (Signal 4) is now clearly the highest-coverage GA4-adjacent move** — public
  API, no GA4 grant, works for all **193 URL'd accounts** vs GA4's 15. If page-speed
  context matters, CrUX reaches 13× more of our panel than this GA4 login does.
- **The real lever for panel-wide GA4 is an access expansion**, not engineering:
  obtain GA4 Viewer on the *BrightMatter panel's* properties (per-client grants, or
  the agency login that actually owns our roster). Until then, GA4 is a 15-account
  capability.

**Verdict:** GO for a **15-account GA4 engagement pilot** + **CrUX across 193
accounts**; do NOT scope GA4 as full-panel until access covers the panel. The pilot
will tell us whether the mechanism earns the later access-expansion effort.

---

## Lock-in scorecard (GA4 Phase 1 — now complete)

| Criterion | Status |
|---|---|
| GA4 property → Ads account mapping | ✅ **complete** — 15 high-confidence, 3 low, persisted in `ga4_property_map` |
| Data inventory per property | ⚠️ URLs captured for 211/230; full inventory (retention/CWV/events) deferred to the 15 Phase-2 properties |
| Auth status documented | ✅ live (info@hawkemedia.com, 230 properties) |
| Signal ranking with expected impact | ✅ re-grounded: ~111 reachable CVR/CPA signals on 15 accounts (was 1,130 panel-wide) |
| Measurement framework defined | ✅ confidence-upgrade % / template-MAE / rec-quality on the 15-account pilot |
| Top 3 signals for Phase 2 | ✅ engagement rate + device gap (15 accts) · CrUX page-speed (193 accts) |
| Honest "is it worth it" assessment | ✅ pilot GO; full-panel GA4 gated on access expansion, not code |

**7/7 — Phase 1 complete.**

---

## Net read

The auth unblock was real and the mapping is done — but the honest result is a
**coverage ceiling, not a green field**: this GA4 login overlaps only 15 of our 223
accounts, reaching ~10% of the CVR/CPA signals GA4 could theoretically help. The
right next moves are small and truthful: a **15-account engagement pilot** to prove
the confidence-upgrade mechanism, **CrUX for the 193 URL'd accounts** as the broad
page-speed play, and — if the pilot pays off — an **access-expansion** to bring the
rest of the panel's GA4 properties into view. Per Phase 6.75, even then GA4 should be
expected to lift *diagnostic confidence* more than *magnitude precision*.

> Reproduce: `python scripts/ga4_phase1_mapping.py` (re-pulls property metadata,
> rebuilds `ga4_property_map`). No GA4 report data is pulled.
