# Phase 2 — Time Series & Historical Analysis: Findings & Changelog

*Run date: 2026-06-19. Branch: `main`. All outputs computed end-to-end via
`scripts/phase2_run.py` against the live ingested data.*

---

## Run parameters (what was analyzed)

| Parameter | Value |
|---|---|
| Accounts (with daily metrics) | **153** |
| Campaigns | **9,579** |
| Date range | **2026-03-30 → 2026-06-14** (77 days) |
| Daily metric rows | **393,306** |
| Total spend (window) | **~$13.66M** |
| Total conversions (window) | **728,217** |
| Change events | **131,434** (60,313 auto-applied / 71,121 human) |
| Search terms ingested | **149,942** across 139 accounts |
| Episodes (change→outcome) | **3,928** |
| Phase-1 signals | **8,796** |

**Compute:** OLS trends (scipy.linregress), PELT regimes (ruptures L2). Full
Phase 2 run ≈ 3.7 min (trend recompute dominates at ~150s). No new ingestion —
Phase 2 works entirely on already-ingested data.

**Data caveats that shape every finding below:**
- Only **77 days** of *daily* data — short for time-series, and far short of the
  12 months needed for internal seasonal curves.
- Daily campaign metrics are **highly noisy** (esp. CPA/CVR on low-volume days).
- Outputs are **PRELIMINARY**: trend-adjusted, never causal.

---

## Changelog (Phase 2 + episode foundation)

| Commit | What |
|---|---|
| `737b4c3` | Phase 1.5 — batched change→outcome episodes with confidence framing |
| `69d1a8e` | Phase 1.75 — change-bundle recovery + bundle→performance cards |
| `6241bd9` | **2.1** — rolling OLS trend detection → `campaign_trends` |
| `fdde223` | **2.2** — annotate Phase-1 signals with campaign-trend context |
| `da2b93f` | **2.3** — trend-adjusted episode attribution |
| `97b1fa1` | **2.4** — regime change detection (PELT) → `regime_changes` |
| `dedd0ff` | **2.5** — volatility profiling + threshold multipliers (applied to `cpa_spike`) |
| `b0879dc` | **2.6** — external seasonal baselines (monthly CPA index by vertical) |
| `bb3fd30` | `scripts/phase2_run.py` — coherent end-to-end runner + verification |

New deps: `numpy`, `scipy`, `ruptures`. New tables: `campaign_trends`,
`regime_changes`. New columns on `signals` (trend context) and `episodes`
(trend-adjustment). New config: `config/seasonal_baselines.yaml`.

---

## Data findings

### Signals (8,796) — Phase 1 detectors, now trend-annotated
- Confidence tiers: **358 CONFIRMED · 1,461 LIKELY · 6,977 SUGGESTIVE**
- Severity: 108 critical · 7,180 warning · 1,508 info
- **`insufficient_conversions_for_strategy` = 6,710 — 76% of all signals.**
  Then: cvr_change 521, cpa_change 385, budget_capped_change 279, cvr_drop 163,
  auto_applied_changes 124, budget_capped 75, budget_limited_is 64.
- **Trend context (2.2)** on metric-based signals: 1,358 "highly variable",
  247 "30d stable", 88 "30d improving", **63 "pre-existing decline"** (the drop
  is a continuation, not a new event), 18 "new development". 7,022 structural /
  account-level signals carry "no trend data".

### Trends (2.1) — 61,358 rows; 14-day window
- volatile **12,186** · stable **8,910** · directional **999**
  (declining 596, improving 271, falling 74, rising 58).
- **Only ~4.5% of campaign-metrics have a callable direction** — daily data is
  too noisy at the campaign level to call a trend most of the time.

### Regime changes (2.4) — 9,613 across 4,092 campaigns
| Metric | Count | Up / Down |
|---|---|---|
| impression_share | 4,104 | 2,492 / 1,612 |
| cost | 2,980 | 1,441 / 1,539 |
| cvr | 1,088 | 454 / 634 |
| roas | 957 | 387 / 570 |
| **cpa** | **484** | 292 / 192 |
- IS and cost shift most (budget/competition); **CPA regimes are rarest (484)
  and the most actionable** — datable structural shifts ("CPA stepped from $30
  to $42 on Apr 15 and stayed there").

### Volatility (2.5) — CPA metric (drives `cpa_spike`)
- high **1,110** · medium 186 · low **8**. Daily CPA is overwhelmingly noisy →
  most spike thresholds are widened ×1.5 to avoid false alarms.

### Episodes + trend adjustment (2.3) — 3,928
- improved 902 · degraded 1,077 · neutral 834 · confounded 1,115.
- trend_adjusted on 2,357 attributable episodes, but **only 43 had a
  statistically real pre-trend to subtract; 19 flipped outcome.**

---

## The headline finding: auto-apply tilts negative

Bundle → performance cards (clean/attributable episodes, trend-adjusted):

| Bundle | n / accts | imp / deg / neu | Tilt |
|---|---|---|---|
| `auto_creative_budget` | 66 / 10 | 26% / **52%** / 23% | **degrades** |
| `auto_comprehensive_optimization` | 35 / 9 | 26% / **49%** / 26% | **degrades** |
| `asset` (auto) | 413 / 75 | 28% / 42% / 30% | degrades |
| `budget` (auto) | 1,045 / 85 | 35% / 41% / 23% | degrades |
| `auto_budget_optimization` | 135 / 32 | 30% / 35% / 36% | degrades |
| `auto_targeting_restructure` | 53 / 18 | 28% / 36% / 36% | degrades |
| `ad_creative` (auto) | 87 / 25 | 33% / 41% / 25% | degrades |
| `auto_budget_expand` | 50 / 14 | 42% / 44% / 14% | mixed |
| `campaign_setting` / `targeting_keyword` | 460 / 406 | ~32% / ~32% | mixed |
| `auto_campaign_refresh` | 38 / 9 | 37% / 32% / 32% | **improves (only one)** |

**Across 153 accounts, every auto-applied bundle except `auto_campaign_refresh`
degrades performance more often than it improves it** — worst being
`auto_creative_budget` (52% degrade) and `auto_comprehensive_optimization`
(49%). This is quantified, multi-account evidence for the expert consensus that
Google's auto-apply usually hurts the advertiser — the novel finding the system
was built toward. **Preliminary** (see caveats); to be hardened in Phase 3+.

---

## What we expected but didn't get

1. **Trend adjustment barely moved anything.** Only 43 of 2,357 attributable
   episodes had a real pre-trend to subtract; 19 flipped. The bundle cards
   shifted marginally (auto_budget_optimization 39%→35% degraded). This is the
   spec's own decision point answered: *trend adjustment is low-yield at 60 days*
   — daily campaign data is too short/noisy for significant short-window
   pre-trends. It will matter more as history accumulates.

2. **Almost no callable trends** — 999 directional of 22,095 (4.5%). Expected
   richer "this is trending" coverage; the engine correctly refuses to call a
   direction on noisy daily data, so trend context is thinner than hoped.

3. **The volatility hypothesis was wrong as stated.** Low cost-CV turned out to
   mean *flat/dead* campaigns (median spend $0), not "stable brand/large
   campaigns." Per-metric volatility (CPA) preserved the mechanism for
   `cpa_spike`, but the assumed campaign-stability story didn't hold.

4. **`insufficient_conversions_for_strategy` floods at scale.** A clean MONITOR
   detector at 45 accounts (43 signals) became **6,710 signals (76% of the set)**
   at 153. Most small Smart-Bidding campaigns convert <15/mo — technically true,
   operationally drowning. Detectors validated at 45 accounts don't keep their
   signal-*volume* profile at 153; this one needs a relevance/spend gate and a
   re-validation at scale.

5. **No internal seasonal baselines.** 2.6 is entirely an external proxy
   (WordStream/Triple Whale). 77 days is nowhere near the 12 months needed to
   build BrightMatter's own per-vertical curves.

6. **The "lower false-positive rate" lock-in item is unproven.** Volatility
   widens `cpa_spike` thresholds, but no rigorous before/after FP measurement
   was run. Phase 2.7 is therefore PARTIAL on this item.

7. **Cross-process boolean staleness** (a DuckDB WAL quirk) made
   `trend_adjusted`/`confounded` read as 0 from fresh connections until an
   explicit `CHECKPOINT`. Resolved, but it cost time; `phase2_run.py` now
   checkpoints and verifies in-process.

---

## Net read & next steps

The **bundle → performance cards are the genuine deliverable** — directional,
multi-account evidence that auto-apply tilts negative. The time-series
*adjustment* layer added little on top of the raw 1.75 cards because the data is
too short for short-window trend isolation to bite — an honest result, not a
failure. The most valuable *new* Phase-2 artifact is **regime changes** (484
datable CPA structural shifts) — concrete anchors Phase 3/4 can attach episodes
to.

**Recommended next:**
- Gate `insufficient_conversions_for_strategy` so it stops flooding (relevance /
  spend floor), and re-validate at 153 accounts.
- Close 2.7 with a rigorous false-positive before/after measurement.
- Proceed to **Phase 3 — Segment-Scoped Learning** (consumes the trend-adjusted
  episodes for cross-account patterns with confidence intervals).

> Note: the populated tables live in the gitignored local DuckDB; this repo
> carries the code + `scripts/phase2_run.py` to regenerate them (~4 min).
