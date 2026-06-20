# Phase 4 — State-Conditioned Templates & Historical Backtesting: Findings

*Run date: 2026-06-19. Branch: `main`. Computed end-to-end via `scripts/phase4_run.py`
(catalog + shadow) and `scripts/phase4_recommend.py` (recommendations), on the
223-account / 4,889-episode panel. No LLM anywhere in the inference loop —
templates are episode aggregation + k-fold cross-validation.*

---

## What Phase 4 built

A programmatic template engine: every episode is tagged with the campaign's
*pre-change performance state*, then state × action combinations are enumerated
into templates that predict "given this state and this action, CPA will move by
X%." Each template is validated by 5-fold cross-validation and activated by
measured accuracy. New module `brightmatter/patterns/templates.py`; new tables
`templates`, `template_predictions`; episode columns `pre_state`,
`own_cpa_ratio`, `bench_cpa_ratio`.

---

## Run parameters

| Parameter | Value |
|---|---|
| Episodes available | 4,889 |
| Episodes usable (readable CPA pre+post, state-tagged) | **4,185** |
| Templates extracted | **147** |
| — ACTIVE (dir-acc > 55%) | **45** (mean 66% direction accuracy) |
| — PROVISIONAL (active, < 15 episodes) | 31 |
| — SHADOW_ONLY (45–55%) | 24 |
| — RETIRED (< 45%) | 47 |
| Single-action / multi-action templates | 69 / 78 |
| Granularity (level 0 sharpest → 3 broadest) | 17 / 30 / 65 / 35 |
| Backtest predictions logged | 3,864 |
| Live (shadow) predictions logged | 895 |

**State distribution:** performing_well 43% · volatile 33% · above_average 13% ·
stable 4% · crisis 4% · struggling 2% · declining/recovering <1%.

---

## Changelog

| What | Where |
|---|---|
| **4.0** state bucketing (70% own-history / 30% benchmark weight) + episode tags | `templates.py: classify_state/tag_episode_states`, `database.py` |
| **4.1** exhaustive template extraction with granularity cascade (sharpest qualifying cell, no double-count) | `templates.py: extract_templates` |
| **4.2** 5-fold CV backtesting; direction + magnitude buckets; activation bands | `templates.py: kfold_score/backtest_templates` |
| **4.3** catalog + versioning tables; live-state doc generator | `templates.py: persist_templates/write_live_state_doc`, `docs/phase-4-live-state.md` |
| **4.4** shadow simulation (temporal holdout, predict-before-outcome) | `templates.py: shadow_simulate` |
| **4.5** recommendation generation | `templates.py: recommend`, `scripts/phase4_recommend.py` |

No new dependencies. CPA convention: signed change `(post−pre)/pre`, negative =
improvement, winsorized to `[−1, +3]` so tiny-denominator artifacts (CPA $1→$50)
can't dominate medians or MAE.

---

## What worked

### State bucketing is meaningful and verifiable
Spot-checks confirm the logic: every `crisis` episode has own-CPA-ratio ≥ 2.0,
every `performing_well` episode is ≤ 1.0 on both own-history and benchmark,
`above_average` is ≤ 1.0 own / > 1.0 benchmark. No state exceeds 60% (lock-in
4.6). 3,864 episodes carry a usable state + outcome.

### The headline pattern: state predicts action outcome, intuitively
The strongest active templates are the ones a senior strategist would nod at:

| State × action | Prediction | Backtest dir-acc | n |
|---|---|---|---|
| crisis → campaign_setting change | CPA **improves −61%** | 100% | 15 |
| crisis → budget change (lead_gen) | CPA **improves −61%** | 86% | 42 |
| performing_well → budget change (lead_gen) | CPA **degrades +69%** | 79% | 121 |
| above_average → budget change (ecommerce) | CPA **degrades +53%** | 81% | 26 |
| performing_well → asset change (ecommerce/collectibles) | CPA **degrades +40%** | 78% | 18 |

The system independently learned **"don't touch winners; intervene on losers"** —
changes to already-healthy campaigns degrade CPA, changes to crisis campaigns
improve it. This is the most actionable output BrightMatter has produced.

### Recommendations are specific and programmatic
For each campaign, `recommend()` matches its current state to active templates and
emits e.g. *"budget change → predicted CPA degrades +22% (range +11% to +60%);
basis 31 episodes / 11 accounts, backtest 74% direction."* No LLM scores or
generates any of it — it's a SQL match plus a stored median.

### Multi-action templates carry their weight
78 of 147 templates are multi-action (`change_count > 1`). Including confounded
episodes as their own category (rather than discarding them) produced usable
patterns — e.g. `auto_creative_budget` multi-action in volatile ecommerce
(+25%, 71% dir).

---

## What we learned (and the big honest caveat)

### The crisis/performing_well patterns are partly regression to the mean
This is the most important caveat in Phase 4. A campaign whose CPA is 2× its own
average (**crisis**) will tend to revert toward its average *regardless of any
change* — and a campaign at its best (**performing_well**) will tend to drift
worse. So "crisis → action improves CPA −61%" and "performing_well → action
degrades +69%" **conflate the action's effect with mean-reversion**. The templates
are honest *predictions* ("if you're in this state and do this, CPA tends to move
this way") but they are **not** clean causal estimates of the action. Phase 2's
trend-adjustment removes *linear* pre-trends from the magnitude, but not
mean-reversion conditioned on an extreme starting state. This is a known limit of
state-conditioned templates, flagged here rather than papered over.

### Direction is learnable; exact magnitude is not (yet)
Active templates predict direction at 66% (vs 33% random across 3 classes), but
magnitude is mostly "miss": in the shadow simulation, 677 of 895 predictions were
>20pp off, with only 65 "exact" (≤5pp). Daily CPA is too noisy for sharp magnitude
at this data volume — exactly what the spec anticipated shadow tuning would
converge over time.

### Shadow simulation shows real, modest drift
Templates trained on older episodes and tested on the most-recent ~3 weeks scored
**58% live vs 67% backtest direction accuracy** — a 9pp optimism gap. They still
beat random and clear the 55% bar, but backtest accuracy overstates live
performance. The drift-detection harness (live-vs-backtest, weekly) is the
mechanism to catch this going forward.

---

## What we expected but didn't get

1. **80+ ACTIVE templates (lock-in target).** Got **45 ACTIVE** (+ 31 PROVISIONAL
   = 76 usable). The 55%-direction bar on a 3-class outcome is demanding, and
   ~47 combos are genuinely near-random (RETIRED). I did **not** loosen thresholds
   to hit the number — 45 is the honest count, and it grows as episodes accumulate
   (the Phase-5 thesis). Template *count* (147) cleared the 100+ target.

2. **The spec's volatile-first state order had to be reversed.** An absolute
   `CV>0.30` gate tagged 78% of episodes "volatile" (daily CPA is that noisy),
   collapsing the distribution and violating lock-in 4.6. Volatile was demoted to a
   residual so the *performance* signal leads. Deliberate, documented deviation —
   the spec's own "no state > 60%" criterion expresses the true intent.

3. **Clean causal magnitude.** See the mean-reversion caveat — the headline
   patterns are predictive, not causal.

4. **Exact-% predictions.** 76% of shadow predictions miss by >20pp. Direction is
   the usable signal today; magnitude needs the shadow-tuning loop and more data.

5. **Rich coverage of the rare states.** `declining` (5) and `recovering` (4) are
   too thin to template — most episodes are performing_well / volatile /
   above_average. The interesting transitional states are under-sampled.

---

## Lock-in scorecard (4.6)

| Criterion | Status |
|---|---|
| Every episode tagged with pre-change state | ✅ 3,864 usable |
| State distribution meaningful (no state > 60%) | ✅ max 43% |
| 100+ templates at sharp granularity | ✅ 147 |
| 5-fold cross-validation on all templates | ✅ |
| 80+ ACTIVE templates | ❌ **45 ACTIVE** (76 incl. provisional) — documented gap |
| Template catalog with versioning + changelog | ✅ |
| Shadow mode logging predictions before outcomes | ✅ 895 live |
| Drift detection (live vs backtest) | ✅ 58% vs 67% measured |
| Live state doc auto-generating | ✅ `docs/phase-4-live-state.md` |
| Recommendations for 10 real campaigns | ✅ `scripts/phase4_recommend.py` |
| Multi-action templates included | ✅ 78 of 147 |
| Backtest accuracy honest (no leakage) | ✅ each episode tested out-of-fold once; mean-reversion caveat surfaced |

11 of 12 met; the 12th (80+ ACTIVE) is an honest data-volume gap, not a
correctness failure.

---

## Net read & next steps

Phase 4 turns the episode store into **147 validated, versioned, state-conditioned
templates** with measured accuracy and a working shadow loop. The usable signal
today is **direction** ("touching a healthy campaign tends to hurt; intervening on
a crisis tends to help"), delivered as specific per-campaign recommendations. The
honest limits are exact magnitude (needs shadow tuning + data) and the
mean-reversion confound on extreme-state templates.

**Recommended next (Phase 5 territory):**
- Keep ingesting — more episodes lift PROVISIONAL → ACTIVE and tighten magnitude.
- Run the shadow loop continuously so magnitude medians converge against live data.
- Add a mean-reversion control (compare action episodes to a matched no-action
  baseline in the same starting state) to separate action effect from reversion.

> Populated tables live in the gitignored local DuckDB; this repo carries the code
> + scripts to regenerate (`scripts/phase4_run.py`, ~seconds on 4,185 episodes).
