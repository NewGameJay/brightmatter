# Phase 4.75 — Matched Controls & the Act-vs-Wait Framework: Findings

*Run date: 2026-06-19. Branch: `main`. Computed via `scripts/phase4_75_run.py` on the
223-account / 4,185-episode panel + 10,027 no-action baseline windows. Purely
programmatic — no LLM in the inference loop.*

Phase 4.75 upgrades the 4.5.1 population counterfactual to within-campaign matched
controls, builds the act-vs-wait decision framework, validates the search-terms
detector, and resolves the weekly-CPA question. New module `patterns/actwait.py`;
new table `matched_controls`.

---

## 4.75.1 Matched controls — the population finding was partly selection bias

For every episode we searched for a no-action window on the **same campaign, same
state**, non-overlapping and within 60 days — the campaign as its own control,
removing the cross-campaign selection bias of 4.5.1.

**Match rate: 51%** (2,115 of 4,185 episodes — above the 30% target). The
within-campaign estimates differ materially from the population ones:

| State | Matched attribution | Population (4.5.1) | n (matched) |
|---|---|---|---|
| performing_well | **−7pp** (action slightly *better*) | +5pp (worse) | 893 |
| volatile | **+11pp** (worse) | +5pp | 886 |
| above_average | −0pp | +0pp | 254 |
| stable | +31pp (worse) | +9pp | 49 |
| crisis | −21pp (action better) | +7pp | 31 |

**This walks back part of the 4.5.1 headline.** The population claim — "action is
uniformly ~5–9pp worse than inaction" — does *not* hold within-campaign. On the
two robustly-sampled states the matched estimates even disagree in *sign*:
performing_well looks slightly better with action (−7pp), volatile clearly worse
(+11pp). crisis flips to −21pp (action better) but on only 31 matched pairs.

The honest, revised conclusion: **action effects are small and state-dependent,
not a clean universal penalty.** The dramatic 4.5.1 "do nothing is always better"
was inflated by selection bias (advertisers act precisely when they sense
trouble, so the population no-action group was systematically healthier). Matched
controls are the more trustworthy estimate, and they say: it depends on the state,
and most effects are modest. Where matched and population disagree, **trust
matched** — and the per-campaign recommendation below uses it directly.

---

## 4.75.3 Act-vs-wait framework — the product vision, working

Every recommendation now leads with the **do-nothing forecast** (the natural
trajectory for the campaign's state) and compares it to the template prediction,
preferring the campaign's own matched control when one exists. `action_cost =
acting − waiting` (positive = acting leaves CPA higher). Decisions: `DO_NOT_ACT`
(≥20pp worse), `WAIT` (10–20pp worse), `EITHER` (±10pp), `ACT` (≥10pp better).

**Template categorization** (using the 4.5.1 population attribution as the
population-level lens):

| Category | Count | Meaning |
|---|---|---|
| do-nothing (action ≈ natural) | 21 | waiting is fine |
| **don't-do-this** (action ≥10pp worse) | **42** | real harm beyond gravity |
| **act-now** (action ≥10pp better) | **13** | action genuinely beats waiting |

Top **don't-do-this** (real action harm, not mean reversion):
- `auto_comprehensive_optimization · lead_gen · performing_well` → **+149pp** beyond natural (n=11)
- `auto_creative_budget · lead_gen · performing_well` → +116pp (n=13)
- `budget · lead_gen · performing_well` → +51pp (n=121, the robust one)
- `budget · ecommerce · above_average` → +48pp (n=26)

Top **act-now** (action beats inaction):
- `campaign_setting · stable` → −58pp (n=11)
- `budget · lead_gen · pool_spa · 5k-25k · volatile` → −44pp (n=13)
- `campaign_setting · lead_gen · above_average` → −26pp (n=48)

Sample recommendations (do-nothing forecast always shown):
```
360 Cookware (food_beverage/ecommerce) — state=above_average
  do-nothing forecast: CPA +5% | with budget change: +53% | action cost +88pp
  same-campaign matched control (n=7): +88pp
  >>> DO_NOT_ACT: acting leaves CPA ~88pp higher than doing nothing.

FragranceBuy CA (beauty/ecommerce) — state=performing_well
  do-nothing forecast: CPA +18% | with budget change: +18% | action cost −1pp
  >>> EITHER: acting and waiting are within 1pp — no strong preference.
```

Most healthy/volatile campaigns return **EITHER** (acting ≈ waiting) — which is
the correct, honest answer most of the time. The framework's value is isolating
the few **DO_NOT_ACT** cases (specific, matched, large-cost) and the **act-now**
templates. That is the "when to act vs. when to wait" advisor the spec set out to
build.

**Coherence note:** template *categorization* uses the population natural baseline
(a population-level statement); per-campaign `should_act()` upgrades to the
matched control when available. Given 4.75.1 showed the population baseline carries
selection bias, treat the 42/13 category counts as directional and defer to the
matched per-campaign control for any real recommendation.

---

## 4.75.2 Search-terms mining (existing data)

The long-scaffolded `search_terms_waste` detector finally has data: **293,875
terms across 191 accounts, $3.9M of term-level spend.**

- **Material waste: $352K across 1,780 terms** that each spent >$100 with **zero
  conversions** — the defensible, actionable signal.
- The raw "$2.1M / 55% of spend on zero-conversion terms" figure is **not** used as
  the headline: most individual long-tail queries never convert, so that number
  overstates waste. The >$100-and-zero-conv cut is the honest materiality floor.

This validates the detector concept; wiring per-term waste as an episode attribute
(linking keyword-addition episodes to the terms they generated) is deferred — it's
complex and low-value for the act-vs-wait core.

---

## 4.75.4 Weekly CPA — already in place

The spec proposed switching templates from daily to weekly CPA to reduce noise.
**Episodes already use a 7-day aggregate CPA** — `pre.cpa = sum(cost)/sum(conv)`
over the 7-day pre window, likewise post. So the magnitude is already weekly-to-
weekly; the convergence noise seen in 4.5.4 is **cross-episode dispersion and low
conversion counts in some windows**, not daily sampling. No rebuild needed. A
14-day basis would smooth further at the cost of responsiveness — a future toggle,
not a fix for a problem that the 7-day aggregate already addresses.

---

## Deferred: the 5 new-segment detectors (4.75.2 items 5–9)

Five of the nine proposed detectors — **device split, search-partners, day/hour,
geographic outliers, RSA ad-strength** — require **re-ingesting all 210 accounts
with new GAQL segments**. Device/geo/hour splits in particular multiply
`daily_metrics` row counts many-fold and are an hours-long, quota-heavy ingestion.

Given (a) exception mining returned a clean null at 223 accounts, so adding
dimensions is speculative, and (b) the act-vs-wait core is complete without them,
these are **deferred pending an explicit decision** rather than run on spec. They
are worth doing if the goal shifts to sharper exception mining; they are not on the
critical path to the advisor. (The four *existing-data* detectors — search-terms
mining done above, plus conversion-counting / budget-allocation / attribution-model
checks — are quick follow-ups on data already in hand.)

---

## Lock-in scorecard (Phase 4.75)

| Criterion | Status |
|---|---|
| Matched controls for 30%+ of episodes | ✅ 51% |
| Matched vs population compared honestly | ✅ (revises 4.5.1) |
| 9 detectors built | ⚠️ search-terms validated; 4 existing-data quick; **5 segment detectors deferred** (ingestion decision) |
| Search-terms mining on 293K terms | ✅ $352K material waste |
| Act-vs-wait framework for 10 campaigns | ✅ with do-nothing forecast |
| Do-nothing forecast in every recommendation | ✅ |
| Weekly CPA tested | ✅ already weekly; documented |
| Templates re-categorized do-nothing/don't/act | ✅ 21 / 42 / 13 |
| Exception mining re-run with new dimensions | ⏸️ pending segment-detector ingestion |

7 of 9 fully met; 2 gated on the segment-detector ingestion decision.

---

## Net read & next steps

The centerpiece works: a **matched-control act-vs-wait advisor** that leads with
the do-nothing forecast and isolates the specific, campaign-matched cases where
intervention genuinely helps or hurts. The most important scientific result is the
correction itself — **matched controls show the 4.5.1 "always wait" finding was
partly selection bias; action effects are smaller and state-dependent.** That
makes the advisor more honest, not less useful: it now says "either" most of the
time (correctly) and reserves strong calls for matched, large-cost cases.

**Recommended next:**
- Decide whether to run the 5 segment-detector ingestion (sharper exception mining)
  or proceed to Phase 5 operationalization on the current feature set.
- Phase 5: run the act-vs-wait advisor continuously in shadow mode, scoring
  "we said wait → it reverted" vs "we said don't-act → they acted → it degraded."

> Populated tables live in the gitignored local DuckDB; regenerate with
> `scripts/phase4_run.py` → `phase4_5_run.py` → `phase4_75_run.py`.
