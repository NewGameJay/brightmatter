# Phase 4.5 — From Obvious to Non-Obvious: Findings

*Run date: 2026-06-19. Branch: `main`. Computed via `scripts/phase4_5_run.py` on the
223-account / 4,185-usable-episode panel + 10,027 no-action baseline windows. Still
purely programmatic — no LLM in the inference loop.*

Phase 4.5 stress-tests the Phase 4 templates along four axes: how much is real
action effect vs. regression to the mean (4.5.1), are there conditional exceptions
intuition misses (4.5.2), do patterns transfer to unseen accounts (4.5.3), and
does magnitude tighten with data (4.5.4). New module `patterns/refine.py`; new
tables `baseline_observations`, `template_exceptions`, `magnitude_convergence`;
new template columns `natural_magnitude`, `action_attributable_magnitude`.

---

## 4.5.1 Mean-reversion control — the headline, and it's humbling

For every state we built a **no-action counterfactual**: 10,027 non-overlapping
7d→7d campaign windows with *no change events*, classified into the same states,
measuring the natural CPA trajectory. Then we compared "what happened when you
acted" to "what happened when you did nothing."

| State | Action median | No-action median | Action-attributable | n (act / nat) |
|---|---|---|---|---|
| crisis | **−60%** | **−67%** | **+7pp (worse)** | 170 / 473 |
| performing_well | +23% | +18% | +5pp (worse) | 1,573 / 4,676 |
| struggling | +8% | −0% | +8pp (worse) | 95 / 60 |
| stable | −0% | −10% | +9pp (worse) | 198 / 325 |
| volatile | −6% | −11% | +5pp (worse) | 1,578 / 3,563 |
| above_average | +5% | +5% | +0pp | 563 / 918 |

**The Phase 4 headline was mostly gravity.** "Crisis → change → CPA improves 61%"
was almost entirely regression to the mean: crisis campaigns that received *no
change at all* improved **67%** on their own — slightly *more* than the ones that
were touched. Across every well-sampled state, taking action produced CPA
outcomes **~5–9pp worse than doing nothing**. The sign is remarkably consistent:
intervention, on average, underperforms inaction once mean-reversion is removed.

This both deflates and strengthens earlier phases. It deflates the "templates
predict the *effect of actions*" claim — much of the measured movement is
reversion. It strengthens the Phase 2–3 thesis: changes (auto *and* human) don't
just "degrade more than they improve" — controlling for reversion, they cost
~5–9pp of CPA relative to leaving the campaign alone.

**But the control also finds where action genuinely matters.** Per-template
attribution (the template's own prediction minus its state's natural drift)
separates real effects from gravity:

| Template | Predicted | Natural drift | Action-attributable |
|---|---|---|---|
| budget · lead_gen · performing_well | +69% | +18% | **+51pp (real, large harm)** |
| budget · ecommerce · collectibles · performing_well | +35% | +18% | +17pp |
| budget · ecommerce · performing_well | +18% | +18% | **~0pp (pure drift)** |
| budget · lead_gen · crisis | −61% | −67% | +6pp (reversion) |

So "budget changes on healthy lead_gen campaigns" is a **real** +51pp degradation
beyond drift — a genuine, large action effect — while "budget changes on healthy
ecommerce campaigns" is indistinguishable from doing nothing. The system can now
tell the difference, and that is exactly the recommendation that's worth money:
*when does acting matter, and when should you just wait?*

**Caveat:** the no-action baseline is a population counterfactual, not a matched
control. Advertisers may intervene precisely when they sense trouble, so action
and no-action windows aren't perfectly comparable. It's a large improvement over
no control, not a randomized experiment.

---

## 4.5.2 Conditional exceptions — an honest null (with one to watch)

For the top 12 ACTIVE templates we mined prediction *misses* for dimension-values
(campaign_type, is_pmax, is_brand, vertical, spend_tier, change_bucket, actor)
over-represented via Fisher's exact test, requiring a cluster of **≥10 episodes
across ≥3 accounts at p<0.05**.

**Result: 0 conditional exceptions at the rigorous bar.** This is a true null, not
a gap in the method — the miner evaluated 130 candidate clusters:
- 6 reached p<0.05, but only 2 also had ≥10 episodes — and **both were confined to
  a single account** (the 3-account guard correctly rejected them as one-advertiser
  quirks, not transferable rules).
- The closest genuine exception — *PMax breaks the pool_spa budget rule* (21
  episodes, 3 accounts) — lands at **p=0.054**, just shy of significance.

So at 223 accounts, the general state×action rules hold across sub-populations; no
non-obvious conditional exception clears the bar. The system **confirms intuition
rather than extending it (yet)** — one of the spec's anticipated outcomes. The
PMax/pool_spa near-miss is the one to revisit as data grows. We did **not** loosen
the bar to manufacture findings.

---

## 4.5.3 Cross-account transfer — patterns partly generalize

Leave-one-account-out CV on the **52 accounts with 20+ episodes**: train templates
with the account entirely removed, predict its episodes.

- **Transfer direction accuracy: 58%** (1,719 matched episodes) vs. the in-sample
  backtest baseline of ~67% — a 9pp drop, matching the shadow-simulation drift.
- By business type: **saas 80%** (n=10, thin), **lead_gen 61%**, app 60%,
  **ecommerce 55%**, local 52%, unknown 41%.
- Worst-transfer accounts sit at 28–40% — below random, i.e. a handful of accounts
  behave *opposite* to the population (their winners survive changes, etc.).

**Read:** templates genuinely transfer to unseen accounts at 58% — useful day-one
intelligence for a new client (well above the 33% three-class random), strongest
for lead_gen, weaker for ecommerce. But they are **not** universal: ~9pp of the
backtest accuracy is account-specific, and a minority of accounts invert the
pattern. Commercial value for onboarding is real but should be quoted at ~58%,
not 67%.

---

## 4.5.4 Magnitude convergence — direction is the ceiling for now

We simulated the shadow loop on existing data: walk each top template's episodes in
change-date order, EMA-update the magnitude on direction-correct observations, track
running MAE.

- **3 of 10** top templates converge (late MAE < early). The clearest:
  `budget·lead_gen·volatile` 101pp → 58pp over 100 observations;
  `budget·lead_gen·crisis` holds ~30pp.
- **7 of 10 are flat or worsen** as observations accumulate — the daily-CPA noise
  floor dominates, and some templates show non-stationarity (later episodes differ
  systematically from earlier ones).

**Read:** at this data volume, magnitude does **not** reliably converge — direction
(~58–66%) is the usable signal, and exact magnitude needs both more observations
and likely a less-noisy basis (weekly CPA, or median-of-last-N instead of EMA). The
spec's pessimistic branch is the accurate one for now.

---

## Lock-in scorecard (Phase 4.5)

| Criterion | Status |
|---|---|
| Mean-reversion baselines for all states | ✅ 10,027 windows |
| Action-attributable separated from reversion (all templates) | ✅ 147 templates annotated |
| Exception mining on top ACTIVE templates | ✅ top 12 |
| 3+ non-obvious conditional exceptions found | ❌ **0 at rigorous bar** (honest null; PMax/pool_spa p=0.054 to watch) |
| Leave-one-out account CV on 20+ accounts | ✅ 52 accounts |
| Transfer accuracy measured vs backtest | ✅ 58% vs 67% |
| Magnitude convergence tracking active | ✅ 815 rows, top 10 |
| Running MAE over observations reported | ✅ text MAE curves |
| Findings documented honestly | ✅ this doc |

8 of 9 met; the 9th (3+ exceptions) is a genuine null at 223 accounts, not a
method failure.

---

## Net read & what it means for Phase 5

Phase 4.5's verdict, stated plainly: **most of what Phase 4 "learned" about extreme
states was regression to the mean; the marginal effect of taking action is small
and, on average, slightly negative (~5–9pp worse CPA than inaction).** That is the
most important and least obvious thing the system has produced — and it points
Phase 5 squarely at a *"when to act vs. when to wait"* advisor:

- **Lead with the no-action counterfactual.** The headline recommendation for many
  campaigns is "do nothing — it will revert on its own." Quantify the cost of
  intervening when reversion would have done the job for free.
- **Surface the templates with large positive action-attribution** (e.g.
  budget·lead_gen·performing_well, +51pp) as the genuine "don't do this" warnings —
  these are real action effects, not gravity.
- **Quote transfer at 58%, lead_gen-first**, for new-client onboarding; flag the
  invert-pattern accounts as needing their own data before trusting templates.
- **Treat magnitude as directional, not decision-grade**, until the live shadow loop
  accumulates months of data or moves to a less-noisy CPA basis.
- A matched-control design (compare action episodes to no-action windows on the
  *same* campaigns in the *same* state) would turn 4.5.1's population counterfactual
  into something much closer to a causal estimate — the highest-value Phase 5 build.

> Populated tables live in the gitignored local DuckDB; regenerate with
> `scripts/phase4_run.py` then `scripts/phase4_5_run.py` (~1 min total).
