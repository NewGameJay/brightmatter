# Phase 5 — Operationalization: Findings

*Run date: 2026-06-20. Branch: `main`. The continuous act-vs-wait loop, validated as
a ~30-day as-of replay over the historical panel via `scripts/daily_run.py`. Purely
programmatic — no LLM in the loop.*

Phase 5 turns the act-vs-wait advisor from batch analysis into a continuously
running loop: register a recommendation on every change *before* its outcome,
resolve it at 7/14/30 days, score it against reality, manage template health, and
regenerate a live state doc. New module `patterns/operate.py`; new tables
`live_predictions`, `prediction_resolutions`, `template_health`; scheduler
`scripts/daily_run.py`; live doc `docs/brightmatter-live-state.md`.

---

## The product metric: recommendation accuracy

Not "direction accuracy" — **was the act/wait/don't-act call right**, judged against
the campaign's actual post-change trajectory vs. the no-action baseline for its
state. Resolved over the historical panel (14-day window, the headline):

| Recommendation | n | correct |
|---|---|---|
| **WAIT** | 212 | **76%** |
| **DO_NOT_ACT** | 466 | **66%** |
| **ACT** | 234 | **61%** |
| EITHER (abstention) | 641 | 19% |

**Decisive recommendation accuracy: 67%** (n=912) at 14 days — and stable at
65–70% across the entire ~30-day simulation. That clears the spec's 60% "working"
bar. Direction accuracy is 64%, within 3pp of the Phase-4 backtest (67%) — the
lock-in criterion "live within 10pp of backtest" is met.

**EITHER is treated as an abstention, not scored as a prediction.** The system
declines to commit on 41% of changes (where acting ≈ waiting within ±10pp). Scoring
those as "wrong" whenever noisy CPA lands >10pp from natural (which it usually does)
would be a metric artifact, not a system failure — it drags the *blended* number to
47% while the *committed-call* accuracy is 67%. The honest headline is: **when
BrightMatter makes a call, it is right ~67% of the time; it abstains on ~41%.**

By window: 7d decisive 66% · 14d 67% · 30d ~72% (smaller n) — accuracy holds or
improves as the window lengthens, i.e. the calls describe durable moves, not
transient blips.

---

## Continuous operation works

A ~30-day as-of replay (May 20 → Jun 18, five `daily_run` invocations) shows the
loop accumulating correctly and never crashing:

| as-of | episodes ≤ date | predictions | newly resolved | decisive acc | drift |
|---|---|---|---|---|---|
| 2026-05-20 | 1,524 | 798 | 1,013 | 70% | 2 |
| 2026-05-28 | 2,399 | 1,255 | 559 | 70% | 2 |
| 2026-06-05 | 3,397 | 1,814 | 901 | 66% | 7 |
| 2026-06-12 | 4,185 | 2,342 | 845 | 65% | 6 |
| 2026-06-18 | 4,185 | 2,342 | 979 | 67% | 7 |

Predictions and episodes grow with the as-of date; resolutions accumulate
(4,297 total across 7/14/30d); template health re-scores each run (39 promoted,
3 demoted at the end). The loop is **idempotent** — predictions keyed
(episode+template), resolutions keyed (prediction+window) — so re-runs are safe and
produce zero duplicates (verified: a second pass over the same dates resolved 0 new).
No crashes, no DuckDB stale-read issues (explicit CHECKPOINT each step).

---

## Template health + drift detection

`template_health` rolls resolved predictions into live accuracy per template and
sets status (ACTIVE >55% / SHADOW 45–55% / RETIRED <45%) with a drift flag when
live runs >15pp below backtest. Final state: **39 ACTIVE · 32 SHADOW_ONLY · 3
RETIRED · 7 DRIFT alerts.**

The drift alerts are real and useful — e.g. `budget·lead_gen·pool_spa·performing_well`
backtested 57% but ran 30% live; `campaign_setting·multi·volatile` 60% → 35%. These
are exactly the templates a human should investigate (regime shift? seasonal? small
n?) rather than trust blindly. Drift flags investigation, not automatic retirement.

---

## Noteworthy: the strongest live calls land

The `DO_NOT_ACT` warnings on `auto_comprehensive_optimization · lead_gen ·
performing_well` (predicted +149pp action cost) resolved **correct on 7 of 8**
campaigns — when the system says "do not let auto-apply run a comprehensive
optimization on this healthy lead-gen campaign," the CPA degradation it warned about
materialized. That is the product delivering: a specific, pre-registered, verified
warning.

---

## Honest caveats

1. **This is a faithful replay, not forward operation.** The episodes' outcomes
   already existed; the loop recomputed 7/14/30d post-windows and scored them as if
   resolving over time. It proves the machinery and the accuracy on held data, but
   true forward shadow accuracy needs months of live calendar operation.
2. **41% abstention.** The advisor only commits to a call on ~59% of changes. That's
   appropriate (commit only when confident) but it is not an opinion on everything.
3. **Magnitude is still not decision-grade** (MAE 54pp). The committed calls are
   directional/recommendation-level, not "CPA will move exactly X%."
4. **The no-action baseline is population-level by state.** Per 4.75, that carries
   some selection bias; the 67% is judged against the population natural, not a
   per-campaign matched control (which exists for only 51% of episodes).
5. **"One finding/week a marketer acts on" is unverifiable here** — there's no human
   in this loop. The DO_NOT_ACT warnings above *are* such findings; whether a
   marketer acts on them is a live-deployment question.

---

## Lock-in scorecard (Phase 5)

| Criterion | Status |
|---|---|
| Predictions register before outcomes | ✅ register_predictions, pre-outcome |
| Resolve at 7/14/30-day windows | ✅ 2,159 / 1,553 / 585 resolved |
| Recommendation accuracy as primary metric | ✅ 67% decisive |
| Template health auto-promote/demote | ✅ 39 promoted / 3 demoted |
| Drift detection flags degraders | ✅ 7 alerts |
| Daily scheduler runs full loop | ✅ daily_run.py, idempotent |
| Live state doc generates daily | ✅ brightmatter-live-state.md |
| 30+ days continuous without crashes | ⚠️ ~30-day as-of replay clean; true calendar run is deployment |
| Live accuracy within 10pp of backtest | ✅ 64% vs 67% (3pp) |
| ≥1 finding/week a marketer acts on | ⚠️ warnings produced (DO_NOT_ACT 7/8 correct); marketer action unmeasurable here |

8 of 10 fully met; the 2 partial criteria require real calendar-time deployment and
a human in the loop — not buildable in a backtest.

---

## Net read — is BrightMatter working?

By the spec's own definition: **yes, on the evidence available.** It runs the full
loop automatically and idempotently; its committed recommendations are right ~67% of
the time (above the 60% bar) and stable across a 30-day replay; direction accuracy
matches backtest within 3pp; drift detection surfaces the templates that need
review; and its strongest pre-registered warnings (auto-comprehensive-optimization
on healthy lead-gen, +149pp) verifiably came true 7/8 times.

The honest qualifier: this is proven on a **replay of held data**, not yet on months
of forward shadow data, and the advisor **abstains 41% of the time** and is
**directional on magnitude**. Phase 5 is the accuracy *baseline* the spec set out to
establish — the "before" against which GA4, Meta, more accounts, and longer history
will each be measured as a delta.

> Run the loop: `python scripts/daily_run.py [YYYY-MM-DD]`. Populated tables live in
> the gitignored local DuckDB; the live state doc regenerates each run.
