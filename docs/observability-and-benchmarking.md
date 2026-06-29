# Observability & Benchmarking: Running BrightMatter on Itself

*How to produce the per-episode pipeline trace (the BrightMatter Pipeline UI) and the
full-system scorecard — both from real stored data, no fabrication.*

The pipeline UI is a **view**, not new computation. Every one of its 6 stages is
already persisted by the pipeline that produced it. Observability = assembling those
rows per episode; benchmarking = rolling the monitoring stage up across all episodes.

---

## Two commands

```bash
# 1. SYSTEM SCORECARD — benchmark the full system in one call
python scripts/system_benchmark.py              # printed
python scripts/system_benchmark.py --harnesses  # + sweep all detector harnesses (slower)
python scripts/system_benchmark.py --json        # -> docs/system-scorecard.json (dashboards)

# 2. PIPELINE TRACE — the 6-stage observability view for the UI
python scripts/pipeline_trace.py <account_id> <campaign_id>   # one campaign -> JSON
python scripts/pipeline_trace.py --top 5                      # richest campaigns -> docs/pipeline-traces.json
```

`build_pipeline_trace()` emits exactly the shape the React `BrightMatterPipeline`
component consumes (`analysis / changes / patterns / recommendation / decision /
monitoring`), so the UI renders real reasoning, not seed data.

---

## Stage → table mapping (where every UI field comes from)

| UI stage | Real source |
|---|---|
| 1. Analysis (state, signals, metrics, GA4) | `episodes.pre_state`, `signals`, `daily_metrics`, `ga4_landing_pages` |
| 2. Change Detection (events, bundle, confounded, episode) | `change_events`, `episodes` (change_category/change_count/actor/outcome), bundle signatures |
| 3. Pattern Match (template per-metric, do-nothing, matched control) | `per_metric_predictions` (magnitude-aware), `baseline_observations` (natural trajectory), `matched_controls` |
| 4. Recommendation (call, reasoning, trade-off, cost) | `actwait.should_act()` over the magnitude-aware templates + matched control |
| 5. Decision (actor) | `change_events.actor` (auto_applied / human) |
| 6. Monitoring (predicted vs actual, scoring) | `metric_predictions` (resolved), `prediction_resolutions` |

---

## What the scorecard reports (current run)

- **Coverage**: 223 accounts · 10,076 campaigns · 4,889 episodes · 14 GA4 accounts.
- **Signals**: 484 CONFIRMED / 1,515 LIKELY / 331 SUGGESTIVE (+ untiered segment/GA4 signals).
- **Episodes**: 1,080 improved / 1,382 degraded / 969 neutral / 1,458 confounded (29.8%).
- **Templates**: 147 (45 ACTIVE / 31 PROVISIONAL / 24 SHADOW / 47 RETIRED) + 182 magnitude-aware.
- **Recommendations**: 2,342 registered (1,014 EITHER / 710 DO_NOT_ACT / 327 WAIT / 291 ACT) + 25 cross-platform upgrades.
- **Accuracy (14d, the product metric)**: decisive **67%** (n=912), abstain 41%, direction 64%.
  By call: WAIT 76% · DO_NOT_ACT 66% · ACT 61% · EITHER 19% (abstention, not scored).
- **Per-metric MAE**: ctr 22 · clicks 36 · cost 40 · … · cpa 51 · conversions 52 (pp).
- **GA4**: 41 detector signals across 5 types · 240 page trends · 2 page audits.

`--harnesses` adds the validation health: how many detectors are KEEP / MONITOR / REVISE.

---

## Honest gaps (what the UI shows that the system can't yet fully back)

1. **Stage 5 — marketer follow / override / ignore.** We have the *change actor*
   (auto-applied vs human), but **not** whether a marketer saw a BrightMatter
   recommendation and followed, overrode, or ignored it. That requires the
   forward-deployment human-in-loop layer (the "going live to marketers" milestone),
   which isn't built. The trace emits `marketer_response: null` with a status note —
   never a fabricated response.

2. **Stage 4 narrative.** The UI's prose reasoning is illustrative. The trace emits a
   **structured** reason from `actwait` (decision + action-cost + matched-control
   basis), not generated prose — no LLM in the loop.

3. **Per-campaign template match isn't guaranteed.** A campaign whose
   (category × magnitude × segment × state) cell never cleared the episode floor has
   `template_id: null` and an empty per-metric block — honest, not zero-filled.

---

## How this is used

- **Observability**: trace any campaign to see the full reasoning chain end-to-end —
  signal → change → template → recommendation → outcome — for debugging or client review.
- **Benchmarking**: the scorecard is the single source of truth for system health; run
  it after any pipeline change to see the deltas (accuracy, coverage, calibration,
  signal volumes, harness verdicts). It is the live version of every phase findings doc.

> Both read the gitignored DuckDB. Regenerate the underlying data with the phase
> runners, then `system_benchmark.py` / `pipeline_trace.py` reflect the current state.
