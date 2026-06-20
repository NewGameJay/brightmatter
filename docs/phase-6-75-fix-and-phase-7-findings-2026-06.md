# Phase 6.75-Fix (Magnitude Conditioning) & Phase 7 (Proactive Engine): Findings

*Run date: 2026-06-20. Branch: `main`. On the 223-account / 4,185-episode panel via
`scripts/phase6_75_fix_run.py` and `scripts/phase7_run.py`. Purely programmatic — no LLM.*

---

## Phase 6.75-Fix — Action Magnitude Conditioning

6.75 found every metric WEAK (22–62pp MAE) and traced it to templates conditioning
on action *category* but not *magnitude*. The fix: parse the change amount from
`change_event` old/new values, bucket it, re-template. New module
`patterns/magnitude.py`.

**Extraction (6.75.1–2):** regex `amount_micros` (budget), `target_roas` /
`target_cpa_micros` (bid) from the protobuf-text old/new values → % change → 7
buckets (large_decrease … large_increase). Keyword/creative → batch buckets from
`change_count`. Coverage: **1,776 of 1,777 budget episodes** get a magnitude, plus
244 bid-target. Budget bucket spread: large_increase 468, large_decrease 392,
medium_increase 249, medium_decrease 217, …

**The decisive test (6.75.4–5):** does cost become mechanically predictable once the
template knows the budget bucket?

| Budget cost-MAE | value |
|---|---|
| category-only (`budget · state`) | **53pp** |
| magnitude-conditioned (`budget · bucket · …`) | **36pp** |
| improvement | **+17pp** |
| clears <15pp lock-in | **No** |

Overall cost MAE also improved 42pp → 34pp. **Verdict: the magnitude hypothesis is
real but partial — it is a substantial lever (+17pp on budget cost), not the full
answer.** The lock-in "<15pp" is *not* met, and the reason is a genuine finding:

1. **A budget *cap* change is not a *spend* change.** Many campaigns don't spend to
   their cap, so even a "large_increase" only loosely couples to actual cost. The
   `budget·medium_increase·performing_well` template still shows cost +16% with a
   −7%→+88% IQR. The mechanical link the spec assumed (budget→cost) is broken by the
   cap-vs-spend gap.
2. **Buckets are coarse** — `large_increase` is everything >+30% (a +35% and a +200%
   change share a bucket). Finer buckets would help marginally but can't fix #1.

Some fine combos *do* tighten with magnitude (e.g. `budget·medium_increase·
performing_well` **ctr MAE 5pp**), confirming the mechanism works where the metric is
genuinely magnitude-driven — it's just that cost/conversions/CPA carry irreducible
spend-pacing and conversion noise. 182 magnitude-aware per-metric templates persisted
(prefix `mag:`) for Phase 7.

**Lock-in:** magnitude extracted ✅ · buckets applied ✅ · templates re-extracted with
magnitude ✅ · per-metric re-scored ✅ · **cost MAE <15pp ❌ (36pp; +17pp gain,
honest miss)** · recommendations state magnitude ranges ✅. The miss is the cap-vs-
spend finding, not a build gap.

---

## Phase 7 — Proactive Recommendation Engine

Scans every campaign with a known state against the magnitude-aware library and
surfaces three outputs without waiting for a change. New module
`patterns/proactive.py`; doc `docs/brightmatter-proactive.md`.

**Scan results (1,313 campaigns with a known state):**
- **Recommendations: 6,724** (favorable templates, CPA median ≤ −10%)
- **Warnings: 18,986** (unfavorable, CPA median ≥ +10%)
- **Experiments: 6** distinct knowledge gaps
- Coverage: 1,061 campaigns get ≥1 recommendation, 1,252 get ≥1 warning.

Warnings ≫ recommendations (≈3:1) — consistent with the project-long finding that
most actions degrade. (Counts are raw campaign×template matches; a production UI
shows top-N per campaign — the doc already ranks and truncates.)

**The three outputs line up with everything learned, now stated proactively:**

- **Top warning:** `auto_comprehensive_optimization` on performing_well →
  CPA **+111%**, conversions −50%, ROAS −50% (n=12). The strongest don't-do-this
  from Phase 5, now surfaced *before* the action.
- **Top recommendation:** `campaign_setting` change on crisis →
  CPA **−74%**, conversions +125% (n=11). Intervene on losers — the Phase-4 pattern,
  now a proactive "do this."
- **Top experiment:** test `structure` changes in performing_well — **363 campaigns**
  share this gap (templates exist for the action in that state elsewhere, but not for
  these campaigns' segments). Highest-leverage test to run.

**Ranking (per spec):** warnings first (preventing harm > pursuing gain), then
recommendations by favorable CPA + evidence, then experiments by campaigns-in-gap.

**Knowledge-gap detection** ranks tests by how many same-state campaigns would
benefit if the pattern transfers — `structure`/performing_well (363) and
`auto_budget_expand`/volatile (252) are the highest-leverage gaps to fill.

**The compounding loop** reuses Phase 5 / 6.75 infrastructure rather than duplicating
it: a proactive recommendation is a per-metric hypothesis; if a marketer acts, the
change becomes an episode, `daily_run.py` resolves it at 7/14/30d, template accuracy
updates, and an experimental result spawns/strengthens a template. No new machinery —
the proactive scan is a new *read* over the same register → act → resolve → learn loop.

**Lock-in:** daily scan ✅ · pattern-backed recs with per-metric + magnitude ✅ ·
inverse warnings ✅ · experimental hypotheses ✅ · gap detection ranks by
informativeness ✅ · ranked warnings>recs>experiments ✅ · proactive doc auto-generates
✅ · acted-on recs tracked as hypotheses (via Phase 5/6.75 loop) ✅ · compounding loop
wired ✅. **9/9.**

---

## Net read

**Magnitude conditioning is a confirmed, partial lever:** +17pp on budget cost MAE,
but cost stays ~36pp because a budget *cap* isn't a *spend* — an honest refinement of
the spec's mechanical-predictability hypothesis, with the few genuinely magnitude-
driven metrics (ctr) tightening as predicted. **Phase 7 turns the whole template
library into a proactive advisor** that, per campaign, says do-this / avoid-this /
test-this — ranked, evidence-cited, per-metric, and magnitude-specific — and feeds
acted-on recommendations back through the existing resolution loop to compound. The
proactive scan is the product surface the roadmap was building toward; its accuracy
ceiling is the same ~67% decisive / weak-magnitude reality measured in Phases 5–6.

> Regenerate: `scripts/phase6_75_fix_run.py` then `scripts/phase7_run.py`.
> Proactive output: `docs/brightmatter-proactive.md`.
