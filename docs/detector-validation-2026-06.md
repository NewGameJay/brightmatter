# Detector Validation & Phase 1.3 — Change Summary (June 2026)

Branch: `fix/harness-anchor-date` → `main`. This work took the Google Ads
detector suite from a broken validation harness to **all detectors at MONITOR
or KEEP with zero false positives**, then added the two missing critical
detectors from roadmap §1.3.

## TL;DR

| | Before | After |
|---|---|---|
| Detectors at REVISE | 7 | **0** |
| Detectors at TIGHTEN | 1 | **0** |
| Detectors producing zero signals (NO_SIGNALS) | 4 | 1 (scaffold, awaiting data) |
| Total signals in snapshot | 252 (stale) / 424 (old) | **480 + 3 inflation** |
| Disconfirmation harnesses | 15 | **17** |
| False positives across data-backed detectors | many | **0** |

Final board: **KEEP 5 · MONITOR 11 · TIGHTEN 0 · REVISE 0 · NO_SIGNALS 1.**

---

## 1. The anchoring bug (root cause)

The data ends **2026-05-09**; real-world "today" had advanced past it. Two
layers of code filtered on `current_date - N`, so their windows fell entirely
*after* the last data row:

- **10 disconfirmation harnesses** were grading signals against an empty
  window → spurious "weak evidence" / REVISE verdicts.
- **16 state-detectors** in `detectors.py` silently emitted **zero signals**
  once the data was older than their shortest window. This is why a fresh
  regen had lost `cpa_spike`, `cvr_drop`, `budget_limited_is`, `budget_capped`,
  `over_segmentation`, `insufficient_conversions`, `auto_applied`,
  `pmax_low_volume`, `tracking_break`, and `cross_account_outlier` entirely.

**Fix:** both layers now anchor to `MAX(date)` from `daily_metrics` (the
pattern the Phase-2 change-detectors already used). Added `anchor_date()` +
`windowed()` helpers (`validation/_base.py` and `analysis/change_detectors.py`)
and applied them everywhere. No threshold or logic changes in this step.

**Result:** regen restored the full 494-signal set; all 15 harnesses produce
real verdicts; NO_SIGNALS 4 → 0.

> Note: signal regeneration is **not idempotent** — `analyze` inserts signals
> with random UUIDs and no truncate. Always `DELETE FROM signals` (and
> `patterns`) before re-running, or counts double.

---

## 2. Cleared all REVISE detectors (7 → 0)

Each fixed using its own disconfirmation harness's evidence, then
regenerated + re-validated:

| Detector | Fix | Result |
|---|---|---|
| `over_segmentation` | (anchor fix alone surfaced real verdict) → see §3 | — |
| `insufficient_conv` | (anchor fix) → see §3 | — |
| `pmax_low_volume` | **min campaign-age gate (21d)** — was flagging 4–20-day-old PMax campaigns still in ramp (harness T4) | REVISE → MONITOR; 44→30 signals, 14 FPs removed |
| `pmax_low_conv_volume_change` | **harness T4 semantics**: being in the 6-week learning phase is "not yet interpretable" (inconclusive), not a falsification (disconfirm). Was also structurally unsatisfiable in a 40-day window | REVISE → MONITOR |
| `budget_limited` | **min_conv_in_window = 5** — don't claim "more budget = more conversions" on a near-zero-conversion campaign (harness T3) | REVISE → MONITOR |
| `budget_capped` | **conversions counted over full window + min_conv_in_window = 15** (harness T3 meaningfulness bar) | REVISE → KEEP |
| `duplicate_conversions` | **rewrite**: require 2+ primaries in the *same* category AND corroborating inflation (CVR > 50% or value/conv < $1). Was firing on raw count ≥3 across any category (legit multi-goal tracking) | REVISE → MONITOR; 19 → 2 signals, both with real evidence |

---

## 3. Cleared all TIGHTEN detectors (false positives → 0)

| Detector | Fix | Result |
|---|---|---|
| `cvr_change` | **max_single_day_click_share = 0.5** on both windows — the FP was a prior week dominated by one day (mean-reversion noise, harness T4) | → MONITOR; 71→69 |
| `over_segmentation` | **skip accounts whose starving campaigns are predominantly geo-named (≥50%) or type/brand-named (≥60%)** — deliberate splits, not fragmentation (harness T1/T2). Naming heuristics centralised in `analysis/naming.py` so detector & harness share one source of truth | → KEEP; 17→9, Voomi/360 Cookware/Toggl suppressed |
| `insufficient_conv` | **ENABLED-majority + min campaign-age (14d)** — both FPs were a 1-day paused and a 9-day campaign (harness T1/T4) | → MONITOR; 43→15, all survivors ≥30d |

---

## 4. Roadmap §1.3 — two critical detectors

### PMax conversion inflation — BUILT & VALIDATED
`detect_pmax_conversion_inflation`. Compares PMax vs Search CVR within an
account over 30 days; a ≥3× same-account gap (with reliable volume) is the
observable signature of PMax counting conversion actions Search doesn't.

- Fires on 3 of 35 dual-channel accounts.
- **Correctly identified the canonical case — LOCKLY**: PMax CVR 74% vs Search
  3.7% (19.7×), 5 micro-conversion primaries (PAGE_VIEW, BEGIN_CHECKOUT), PMax
  value/conversion just 5% of Search's. Well-supported on all 4 harness tests.
- Harness probes the alternatives: thin-volume noise (T1), no
  micro-conversion / many-per-click mechanism (T2), matching value-per-conv
  (T3), depressed-Search-baseline (T4). Verdict: MONITOR.

### Search-terms waste — SCAFFOLDED, UNVALIDATED
`detect_search_terms_waste`. The #1 published audit finding. **Code-complete
but not validated** — there is no `search_term_view` data ingested yet, so it
produces NO_SIGNALS (not REVISE) until `ingest --search-terms` runs.

Wired end-to-end to activate on the next ingest: `queries.SEARCH_TERMS` GAQL,
`search_terms` table, `pipeline.ingest_search_terms`, `ingest --search-terms`
CLI flag, the detector (guarded to no-op on an empty table), the harness
(click-sufficiency / share-materiality / assisted-conversion caveat), and
thresholds — all marked `confidence: prior` / revisit-on-first-ingest.

---

## 5. Known data gaps (block full validation, documented for follow-up)

- **`daily_budget_micros` is ingested as all zeros.** The harness budget-vs-
  budget utilization tests (`budget_capped` T1, `budget_limited` T4) can't run;
  both detectors currently rest on conversion-volume gates. Fix = ingest
  `campaign_budget.amount_micros`.
- **`search_term_view` not ingested.** Blocks validation of
  `search_terms_waste` (see §4). Fix = `ingest --search-terms` with valid OAuth.

---

## Files touched

- `brightmatter/validation/_base.py` — `anchor_date()`, `windowed()`
- `brightmatter/analysis/change_detectors.py` — shared anchor/windowed; cvr_change single-day guard
- `brightmatter/analysis/detectors.py` — 16 detectors anchored; gates for pmax_low_volume / budget_limited / budget_capped / insufficient_conv / over_segmentation; duplicate_conversions rewrite; new pmax_conversion_inflation + search_terms_waste
- `brightmatter/analysis/naming.py` — **new**, shared campaign-name heuristics
- `brightmatter/validation/*.py` — 10 harnesses anchored; pmax_change T4 semantics; **new** `pmax_conversion_inflation.py`, `search_terms_waste.py`
- `brightmatter/ingestion/queries.py`, `pipeline.py`, `brightmatter/cli.py`, `brightmatter/storage/database.py` — search_term_view ingestion path
- `config/thresholds.yaml` — new/updated threshold blocks with full provenance
- `data/brightmatter.duckdb` — regenerated signal snapshot

All changes verified by `scripts/validate_all.py` and the 13-test suite (passing).
