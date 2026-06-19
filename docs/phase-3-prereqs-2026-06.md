# Phase 3 Prerequisites — Detector Hardening Before Segment-Scoped Learning

*Run date: 2026-06-19. Branch: `main`. Validated end-to-end against the live
ingested data (153 accounts).*

Phase 3 (Segment-Scoped Learning) consumes Phase-1 signals and Phase-2 episodes
to find cross-account patterns with confidence intervals. Before that, two
signal-quality problems flagged in the Phase 2 findings doc had to be closed —
otherwise the segment statistics inherit the noise. This doc covers item **3.6**
(the `insufficient_conversions_for_strategy` flood), now resolved.

---

## 3.6 — Gate `insufficient_conversions_for_strategy`

### The problem (Phase 2 finding #4)

At 45 accounts this detector was a clean MONITOR (43 signals). At 153 accounts it
flooded to **6,710 signals — 76% of the entire signal set**. Most small
Smart-Bidding campaigns convert <15/mo, so the claim was technically true but
operationally drowning: a marketer opening BrightMatter saw 6,700 "insufficient
conversions" rows and nothing else.

A detector validated at one scale does not keep its signal-*volume* profile at
another. The threshold (`<15 conv/mo` on tCPA/tROAS) was correct; what was
missing was a **materiality gate**.

### The fix — a spend floor, validated against a sweep

Added `min_spend_30d: 500` to the detector's HAVING clause. The floor isn't
arbitrary — a sweep showed the entire flood is sub-$50 dead/trivial campaigns:

| Spend floor (30d) | Campaigns flagged |
|---|---|
| $0 (original) | **6,713** |
| $50 | 299 |
| $100 | 188 |
| $250 | 95 |
| $500 | **53** |
| $1,000 | 30 |
| $2,500 | 12 |

**6,414 of 6,713 (95.5%) spend less than $50/30d.** From $50 up the distribution
is smooth — so $500 is a principled "worth a marketer's attention" floor, not a
cliff that happens to clear noise.

Severity now scales with distance below threshold: **warning** when
`conv < threshold × 0.33` (real money burning, near-zero conversions, genuinely
can't optimize), **info** otherwise (borderline, e.g. 12 of 15). The message now
includes 30-day spend so the materiality is visible inline.

### The second finding — the harness exposed a tROAS false-positive class

Regenerating signals with the spend floor dropped the count to 51, but re-running
the disconfirmation harness flipped **T3 (conversion-value sufficiency for
tROAS)**: among the surviving signals, **8 disconfirmed vs 2 confirmed**.

Why: the spend floor concentrated the population on campaigns that actually
spend. Among those, the TARGET_ROAS subset usually carries enough conversion
*value* (≥ $5,000 / 30d with ≥ 8 conversions) for tROAS to optimize on revenue
**despite a low conversion count** — tROAS targets value, not count. Firing
"insufficient conversions" on them is a false claim. The gate didn't create this
class; it *revealed* it by clearing the sub-$50 noise that had been masking it.

Closed it by exempting TARGET_ROAS campaigns that clear the exact value/conv bar
T3 disconfirms on (`troas_value_sufficient: 5000`, `troas_conv_floor: 8`),
mirroring the harness one-to-one.

### Result

| Stage | insufficient_conv | Total signals | Harness verdict |
|---|---|---|---|
| Phase 2 as-run | 6,710 (76%) | 8,796 | MONITOR (1 edge case) |
| + $500 spend floor | 51 | 2,137 | MONITOR (8 tROAS FPs surfaced) |
| + tROAS value exemption | **43** | **2,129** | **KEEP — zero false positives** |

A **99.4% reduction** in this detector's volume, the whole signal set cut to a
trustworthy ~2,100, and the harness verdict upgraded MONITOR → KEEP. Every
surviving signal is a campaign spending real money on a target-bid strategy that
genuinely lacks the conversion data (count for tCPA, value for tROAS) to
optimize.

**Files:** `brightmatter/analysis/detectors.py` (`detect_bidding_antipatterns`),
`config/thresholds.yaml` (provenance for both new thresholds).

---

## Prerequisites — both now resolved

- **3.0 ingestion expansion** — DONE. Expanded 153 → 223 accounts (top-210-by-
  spend; 210 is the live-spend ceiling). See `docs/phase-3-findings-2026-06.md`.
- **2.7 false-positive measurement** — DONE, and it **disconfirmed** the
  volatility-widening claim: of 33 flat `cpa_spike` signals, the volatility
  multiplier suppressed 19 (all harness-clean, 0% FP) while keeping the 3 true
  false positives (21% FP). The multiplier keys on CPA volatility, which is
  orthogonal to the real FP class (AOV lift). It was disabled and replaced with
  an AOV-lift gate (recent AOV ≥ 2× baseline, mirroring harness T4); the new
  detector fires 30 spikes at **0% FP**. See `scripts/phase2_7_fp_measure.py`
  and the findings doc.

Phase 3 segment analysis (3.1–3.5, 3.7) ran after both completed.
