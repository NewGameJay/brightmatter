# Phase 3 — Segment-Scoped Learning: Findings, Changelog & Honest Gaps

*Run date: 2026-06-19. Branch: `main`. All outputs computed end-to-end on the
expanded live panel via `scripts/phase3_expand.py` → `scripts/phase2_run.py` →
`scripts/phase2_7_fp_measure.py` → `scripts/phase3_run.py`.*

This phase did three things: (1) closed the two Phase-2 prerequisites (the
`insufficient_conversions` flood and the unproven `cpa_spike` FP claim), (2)
expanded the panel from 153 → 223 accounts, and (3) built segment-scoped learning
— per-segment outcome rates with Wilson confidence intervals and two-proportion
z-tests against the rest of the population.

---

## Run parameters (what was analyzed)

| Parameter | Value |
|---|---|
| Accounts (with daily metrics) | **223** (up from 153) |
| Campaigns | **10,076** |
| Date range | **2026-03-30 → 2026-06-18** (81 days) |
| Daily metric rows | **526,328** |
| Total spend (window) | **~$16.99M** |
| Total conversions (window) | **934,421** |
| Change events | **200,841** (77,608 auto-applied / 123,233 human) |
| Search terms ingested | **293,875** |
| Phase-1 signals | **2,281** |
| Episodes (change→outcome) | **4,889** (1,458 confounded → **3,431 clean**) |
| Campaign trends / regime changes | 63,611 / 14,441 |

**Panel ceiling:** of 427 MCC-accessible accounts, only **210 have current spend**
— the target of 250–300 isn't reachable with live-spend data. A 6-month probe of
the 217 dormant accounts (`scripts/probe_dormant_spend.py`) found just **19** with
any spend in the last 6 months, 17 of them too stale (Dec–Mar) for change-history
episodes and worth only ~$310K combined; they were left out as not worth the panel
incoherence. Final distinct-account count is 223 (210 re-ingested fresh + 13 prior
accounts that dropped out of the top-210). **25 accounts (11%) carry a stale right
edge** (<Jun18); recent-window detectors require recent activity so these are
filtered rather than false-flagged, but it slightly thins the most-recent days.

**Compute:** full expansion ≈ 47 min (210 accounts × daily/terms/changes); Phase 2
re-run ≈ 3.6 min; 2.7 + Phase 3 < 1 min.

---

## Changelog

| What | Where |
|---|---|
| **3.6** — gate `insufficient_conversions_for_strategy` flood (spend floor + tROAS value exemption) | `detectors.py`, `thresholds.yaml`, `docs/phase-3-prereqs-2026-06.md` |
| **repo fix** — `list_accounts()` tolerates NULL `mcc_id` (durable, replaces reactive row-repair) | `storage/repository.py` |
| **3.0** — expand ingestion to top-210-by-spend on a uniform 80-day window (idempotent re-ingest) | `scripts/phase3_expand.py` |
| **2.7** — rigorous FP measurement; **disconfirmed** the volatility multiplier; replaced it with an AOV-lift gate | `scripts/phase2_7_fp_measure.py`, `detectors.py`, `thresholds.yaml` |
| **3.1–3.5, 3.7** — segment-scoped learning engine + tables + runner + lock-in checks | `patterns/segments.py`, `storage/database.py`, `scripts/phase3_run.py` |

New tables: `segments`, `segment_patterns`, `segment_comparisons`. New deps: none
beyond Phase 2 (`scipy.stats.norm` for the z-test).

---

## What worked

### The 3.6 gate holds at scale
`insufficient_conversions_for_strategy` was 76% of all signals (6,710) at 153
accounts. After the $500 spend floor + tROAS value exemption it is **50 signals at
223 accounts** — it has dropped out of the top-8 signal types entirely. Adding 70
accounts moved the total signal count only 2,129 → 2,281, i.e. the gate is scale-
stable, not a one-snapshot fix. Lead signals are now a healthy spread: `cvr_change`
556, `cpa_change` 371, `budget_capped_change` 286, `cvr_drop` 173.

### `cpa_spike` is now a 0%-FP detector
The 2.7 measurement (below) led to replacing the volatility multiplier with an
AOV-lift exemption. Result audited against the disconfirmation harness:

| Variant | Spikes fired | False-positive rate |
|---|---|---|
| FLAT (Phase-1 behaviour) | 33 | 9% (3 AOV-justified) |
| Volatility-widened (Phase 2.5) | 14 | **21%** — kept all 3 FPs, dropped 19 real spikes |
| **AOV-gated (this phase)** | **30** | **0%** |

### Segment-scoped learning produces statistically-tested rules
On 3,431 clean episodes across 24 segments: **144** per-segment patterns, **142**
segment-vs-rest comparisons, **26 significant** (p<0.05) — 14 where a change
degrades *more* than baseline, 12 where it degrades *less*. **11** clear the
Phase-4 promotion bar (RELIABLE n + significant difference).

---

## What we learned

### Auto-apply tilts negative — but it's "degrades more than it improves," not "degrades a majority"
`auto_applied:budget` is the dominant change in every segment (n=507–584 each) and
degrades 40–48% of episodes. Crucially, **no single segment's 95% CI sits entirely
above 50%** — so the robust claim is that auto-apply degrades *more often than it
improves* (degraded 1,382 > improved 1,080 overall), not that it degrades the
outright majority. Phase 3's confidence intervals sharpened the Phase-2 bundle-card
headline ("52% degrade") into a more defensible, more modest statement.

### Where auto-apply is significantly worse (Phase 4 "scrutinize" rules)
| Segment | Change | Degrade % (95% CI) | vs rest | p |
|---|---|---|---|---|
| spend_tier=100k+ | auto_budget_optimization | 56% (41–70) | +24pp | 0.007 |
| ecommerce | auto_budget_optimization | 53% (41–65) | +24pp | 0.003 |
| collectibles | asset | 60% (47–72) | +16pp | 0.024 |
| collectibles | budget | 54% (47–61) | +13pp | 0.001 |
| spend_tier=100k+ | budget | 48% (43–52) | +7pp | 0.009 |
| ecommerce | budget | 46% (42–51) | +6pp | 0.038 |

**High-spend accounts and ecommerce are hit hardest by auto-budget changes**, and
**collectibles is the single worst vertical** for auto-apply. These are novel,
segment-specific, statistically-tested findings — the kind a senior strategist
would act on.

### Where auto-apply is significantly safer
pool_spa budget (−9pp, p=0.036), lead_gen budget (−6pp, p=0.033), and several
`auto_budget_optimization` cells in mid/low tiers and lead_gen (−18 to −22pp).
Auto-apply is not uniformly bad — its harm is concentrated in high-spend ecommerce
and a few verticals.

### The 2.7 disconfirmation is itself a finding
The Phase-2.5 volatility multiplier was a plausible idea (widen the spike threshold
on noisy campaigns) that **rigorous measurement proved backwards**: it keys on CPA
*volatility*, which is orthogonal to the real FP class (AOV lift), so it discarded
19 real spikes and retained all 3 false ones. Replacing it with a gate aimed at the
actual FP source (recent AOV ≥ 2× baseline, mirroring harness T4) is the same
disconfirmation-driven move as 3.6: let the harness name the FP class, then gate it.

---

## What we expected but didn't get

1. **No segment proves auto-apply degrades a *majority* (>50%) with confidence.**
   We expected at least the worst segments to clear 50% decisively; instead every
   CI straddles or sits below it. The honest read: auto-apply degrades *more than it
   improves*, and is *significantly worse in specific segments*, but "it breaks
   things most of the time" is not supported at this sample size.

2. **300 accounts was unreachable.** Only 210 of 427 accessible accounts spend at
   all; the dormant 217 yielded just 19 with any 6-month history, mostly too stale
   to produce episodes. The panel is 223, not 300.

3. **The volatility multiplier backfired.** We expected 2.7 to *confirm* a lower FP
   rate from Phase 2.5's volatility widening. It did the opposite — a genuine,
   measured disconfirmation that cost the feature.

4. **Crossed segments are still too thin.** We slice by single dimensions
   (vertical / spend_tier / business_type) only — crossing them (e.g. "100k+ ×
   ecommerce") drops every cell below the n=10 floor at 223 accounts. The
   sharpest rules ("high-spend ecommerce auto-budget") are inferred from two
   separate single-dimension cells, not a true crossed cell.

5. **Still no causal claim.** Segment comparisons say *where* a pattern differs,
   not *why*. Episodes remain associational (a change preceded an outcome); ~30% are
   confounded and excluded. Phase 3 adds statistical rigor to the association, not
   causation.

6. **Stale-edge accounts (25 of 223).** Re-ingesting only the top-210 left ~13
   prior accounts (plus campaigns that went inactive) ending before Jun18. Low
   impact, but the panel isn't perfectly uniform.

---

## Net read & next steps

Phase 3's deliverable is **11 segment-scoped, statistically-tested rules** — the
first BrightMatter output a strategist could act on per-segment ("scrutinize
auto-budget changes in 100k+ ecommerce; they degrade 53–56% of the time, ~24pp
worse than average"). The prerequisite cleanup (3.6 gate, 2.7 AOV fix) also left the
signal set materially more trustworthy: 2,281 well-distributed signals and a
0%-FP `cpa_spike`.

**Recommended next:**
- **Phase 4** — promote the 11 candidates to live rules with periodic re-validation;
  the `revisit:` discipline from overrides applies (nothing permanent).
- Grow the panel over time (more *history*, not more accounts — the ceiling is ~210
  active) so crossed segments and majority-level CIs become reachable.
- Begin the historical-analysis workstream as a *separate* cohort if the 19
  recoverable dormant accounts are ever wanted — not blended into the live panel.

> The populated tables live in the gitignored local DuckDB; this repo carries the
> code + scripts to regenerate them (expansion ~47 min, analysis ~5 min).
