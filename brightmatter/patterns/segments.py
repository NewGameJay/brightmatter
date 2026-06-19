"""Phase 3 — Segment-Scoped Learning.

Bundle cards (Phase 1.75) answered "what does this kind of change do, across all
accounts?" Phase 3 asks the sharper question: "does it do something *different*
in this segment than elsewhere, and is that difference real or noise?"

Pipeline:
  3.1 enumerate segments  -> `segments`            (vertical / spend_tier / business_type slices with enough data)
  3.2 per-segment rates    -> `segment_patterns`    (degraded/improved rate + Wilson 95% CI per segment×category×actor)
  3.3 segment comparisons  -> `segment_comparisons` (two-proportion z-test: segment vs the rest of the population)
  3.4 pattern_cards()      -> human-readable synthesis of the reliable, significant patterns
  3.5 promotion_candidates() -> segment patterns tight/large/significant enough to become Phase 4 rules

Statistics are deliberately conservative: proportions carry Wilson score
intervals (well-behaved at small n, unlike normal-approx), comparisons use a
pooled two-proportion z-test, and nothing is called "real" on count alone — a
pattern must clear a sample-size floor AND a significant difference AND a CI that
doesn't straddle the baseline. Built on CLEAN (non-confounded) episodes only.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from scipy.stats import norm

from brightmatter.storage.database import Database

# ── Sample-size / significance gates ──
RELIABLE_N = 30        # episodes for a "reliable" segment pattern
DIRECTIONAL_N = 10     # episodes for a "directional" (watch) pattern
MIN_ACCOUNTS = 4       # a pattern spanning <4 accounts is one advertiser's quirk
MIN_SEG_ACCOUNTS = 3   # a segment needs at least this many accounts to enumerate
ALPHA = 0.05           # significance level for comparisons
Z_95 = 1.959963985     # two-sided 95% z

# The segment dimensions we slice accounts by (single-dimension only — crossing
# them at 210 accounts thins every cell below the sample floor).
SEGMENT_DIMENSIONS = ("vertical", "spend_tier", "business_type")


# ── Statistics ──

def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion k/n. Robust at small
    n and never escapes [0, 1], unlike the normal approximation."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Pooled two-proportion z-test. Returns (z, two-sided p). Tests whether the
    degraded-rate in a segment (k1/n1) differs from the rest (k2/n2)."""
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    p = 2 * (1 - norm.cdf(abs(z)))
    # norm.cdf returns numpy scalars; cast to native Python so DuckDB can bind them.
    return (float(z), float(p))


def _confidence(n: int, n_accounts: int) -> str:
    if n >= RELIABLE_N and n_accounts >= 8:
        return "RELIABLE"
    if n >= DIRECTIONAL_N and n_accounts >= MIN_ACCOUNTS:
        return "DIRECTIONAL"
    return "LOW"


# ── Data loading ──

def _clean_episodes(db: Database) -> list[dict[str, Any]]:
    """All non-confounded episodes joined to their account's segment dimensions."""
    rows = db.fetchall("""
        SELECT e.episode_id, e.account_id, e.change_category, e.actor, e.outcome,
               e.outcome_magnitude,
               COALESCE(NULLIF(a.vertical, ''), 'unknown')       AS vertical,
               COALESCE(NULLIF(a.spend_tier, ''), 'unknown')     AS spend_tier,
               COALESCE(NULLIF(a.business_type, ''), 'unknown')  AS business_type
        FROM episodes e
        LEFT JOIN accounts a ON a.account_id = e.account_id
        WHERE e.outcome <> 'confounded' AND e.outcome <> 'pending'
    """)
    cols = ["episode_id", "account_id", "change_category", "actor", "outcome",
            "magnitude", "vertical", "spend_tier", "business_type"]
    return [dict(zip(cols, r)) for r in rows]


# ── 3.1 Segment enumeration ──

def enumerate_segments(db: Database, episodes: list[dict] | None = None) -> list[dict]:
    """Every (dimension, value) slice with >= MIN_SEG_ACCOUNTS accounts and any
    clean episodes. Writes the `segments` table."""
    eps = episodes if episodes is not None else _clean_episodes(db)
    db.execute("DELETE FROM segments")
    segments = []
    for dim in SEGMENT_DIMENSIONS:
        by_value: dict[str, list[dict]] = defaultdict(list)
        for e in eps:
            by_value[e[dim]].append(e)
        for value, members in by_value.items():
            if value in ("unknown", ""):
                continue
            accounts = {e["account_id"] for e in members}
            if len(accounts) < MIN_SEG_ACCOUNTS:
                continue
            seg_id = f"{dim}={value}"
            segments.append({
                "segment_id": seg_id, "dimension": dim, "value": value,
                "n_accounts": len(accounts), "n_episodes": len(members),
            })
            db.execute(
                """INSERT OR REPLACE INTO segments
                   (segment_id, dimension, value, n_accounts, n_episodes, computed_at)
                   VALUES (?, ?, ?, ?, ?, current_timestamp)""",
                [seg_id, dim, value, len(accounts), len(members)],
            )
    return sorted(segments, key=lambda s: -s["n_episodes"])


# ── 3.2 Per-segment pattern rates with Wilson CIs ──

def compute_segment_patterns(db: Database, episodes: list[dict] | None = None,
                             min_n: int = DIRECTIONAL_N) -> list[dict]:
    """For each (segment, change_category, actor) cell with >= min_n clean
    episodes, the degraded/improved rate and its Wilson 95% CI. Writes
    `segment_patterns`."""
    eps = episodes if episodes is not None else _clean_episodes(db)
    db.execute("DELETE FROM segment_patterns")
    patterns = []
    for dim in SEGMENT_DIMENSIONS:
        # group: (value, category, actor) -> episodes
        cells: dict[tuple, list[dict]] = defaultdict(list)
        for e in eps:
            if e[dim] in ("unknown", ""):
                continue
            cells[(e[dim], e["change_category"], e["actor"])].append(e)
        for (value, category, actor), members in cells.items():
            n = len(members)
            if n < min_n:
                continue
            accounts = {e["account_id"] for e in members}
            deg = sum(1 for e in members if e["outcome"] == "degraded")
            imp = sum(1 for e in members if e["outcome"] == "improved")
            neu = n - deg - imp
            deg_lo, deg_hi = wilson_interval(deg, n)
            imp_lo, imp_hi = wilson_interval(imp, n)
            seg_id = f"{dim}={value}"
            pat = {
                "segment_id": seg_id, "dimension": dim, "value": value,
                "change_category": category, "actor": actor,
                "n": n, "n_accounts": len(accounts),
                "degraded": deg, "improved": imp, "neutral": neu,
                "degraded_rate": deg / n, "degraded_ci_low": deg_lo, "degraded_ci_high": deg_hi,
                "improved_rate": imp / n, "improved_ci_low": imp_lo, "improved_ci_high": imp_hi,
                "confidence": _confidence(n, len(accounts)),
            }
            patterns.append(pat)
            db.execute(
                """INSERT OR REPLACE INTO segment_patterns
                   (segment_id, dimension, value, change_category, actor, n, n_accounts,
                    degraded, improved, neutral, degraded_rate, degraded_ci_low, degraded_ci_high,
                    improved_rate, improved_ci_low, improved_ci_high, confidence, computed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, current_timestamp)""",
                [seg_id, dim, value, category, actor, n, len(accounts), deg, imp, neu,
                 deg / n, deg_lo, deg_hi, imp / n, imp_lo, imp_hi, pat["confidence"]],
            )
    return sorted(patterns, key=lambda p: -p["n"])


# ── 3.3 Segment comparisons (two-proportion z-test) ──

def compare_segments(db: Database, episodes: list[dict] | None = None,
                     min_n: int = DIRECTIONAL_N) -> list[dict]:
    """For each (segment, category, actor) cell, test its degraded-rate against
    the SAME (category, actor) in the rest of the population (segment vs. its
    complement). Surfaces "auto-apply degrades *more* in ecommerce than
    elsewhere" type findings. Writes `segment_comparisons`."""
    eps = episodes if episodes is not None else _clean_episodes(db)
    db.execute("DELETE FROM segment_comparisons")

    # Baseline counts per (category, actor) across the WHOLE population.
    pop: dict[tuple, list[dict]] = defaultdict(list)
    for e in eps:
        pop[(e["change_category"], e["actor"])].append(e)

    comparisons = []
    for dim in SEGMENT_DIMENSIONS:
        cells: dict[tuple, list[dict]] = defaultdict(list)
        for e in eps:
            if e[dim] in ("unknown", ""):
                continue
            cells[(e[dim], e["change_category"], e["actor"])].append(e)
        for (value, category, actor), members in cells.items():
            n_seg = len(members)
            if n_seg < min_n:
                continue
            whole = pop[(category, actor)]
            # complement = whole population for this pattern minus the segment's own
            seg_ids = {e["episode_id"] for e in members}
            rest = [e for e in whole if e["episode_id"] not in seg_ids]
            n_rest = len(rest)
            if n_rest < min_n:
                continue
            k_seg = sum(1 for e in members if e["outcome"] == "degraded")
            k_rest = sum(1 for e in rest if e["outcome"] == "degraded")
            z, p = two_proportion_z(k_seg, n_seg, k_rest, n_rest)
            seg_rate, rest_rate = k_seg / n_seg, k_rest / n_rest
            direction = "higher" if seg_rate > rest_rate else "lower"
            significant = bool(p < ALPHA)
            seg_id = f"{dim}={value}"
            comp = {
                "segment_id": seg_id, "dimension": dim, "value": value,
                "change_category": category, "actor": actor,
                "n_segment": n_seg, "n_rest": n_rest,
                "degraded_rate_segment": seg_rate, "degraded_rate_rest": rest_rate,
                "rate_delta": seg_rate - rest_rate,
                "z": z, "p_value": p, "significant": significant, "direction": direction,
            }
            comparisons.append(comp)
            db.execute(
                """INSERT OR REPLACE INTO segment_comparisons
                   (segment_id, dimension, value, change_category, actor, n_segment, n_rest,
                    degraded_rate_segment, degraded_rate_rest, rate_delta, z, p_value,
                    significant, direction, computed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, current_timestamp)""",
                [seg_id, dim, value, category, actor, n_seg, n_rest, seg_rate, rest_rate,
                 seg_rate - rest_rate, z, p, significant, direction],
            )
    # Most significant, biggest-delta first.
    return sorted(comparisons, key=lambda c: (not c["significant"], -abs(c["rate_delta"])))


# ── 3.4 Pattern cards ──

def pattern_cards(patterns: list[dict], comparisons: list[dict]) -> list[dict]:
    """Human-readable synthesis: reliable/directional segment patterns, annotated
    with whether they differ significantly from the rest of the population."""
    comp_index = {(c["segment_id"], c["change_category"], c["actor"]): c for c in comparisons}
    cards = []
    for p in patterns:
        if p["confidence"] == "LOW":
            continue
        comp = comp_index.get((p["segment_id"], p["change_category"], p["actor"]))
        tilt = "degrades" if p["degraded_rate"] > p["improved_rate"] else "improves"
        card = {
            "segment": p["segment_id"], "change": f"{p['actor']}:{p['change_category']}",
            "n": p["n"], "accounts": p["n_accounts"], "confidence": p["confidence"],
            "tilt": tilt,
            "degraded_rate": round(p["degraded_rate"], 3),
            "degraded_ci": (round(p["degraded_ci_low"], 3), round(p["degraded_ci_high"], 3)),
            "improved_rate": round(p["improved_rate"], 3),
            "vs_rest": None,
        }
        if comp:
            card["vs_rest"] = {
                "rest_rate": round(comp["degraded_rate_rest"], 3),
                "delta": round(comp["rate_delta"], 3),
                "p_value": round(comp["p_value"], 4),
                "significant": comp["significant"],
                "direction": comp["direction"],
            }
        cards.append(card)
    return sorted(cards, key=lambda c: -c["n"])


# ── 3.5 Phase 4 promotion candidates ──

def promotion_candidates(patterns: list[dict], comparisons: list[dict]) -> list[dict]:
    """Segment patterns strong enough to become Phase 4 rules: a RELIABLE sample
    AND a statistically significant difference from the rest of the population —
    the actionable part of a rule is "this segment behaves differently," in
    either direction. `decisive_majority` flags the subset whose CI also clears
    50% (we can additionally claim it degrades the majority of the time)."""
    comp_index = {(c["segment_id"], c["change_category"], c["actor"]): c for c in comparisons}
    candidates = []
    for p in patterns:
        if p["confidence"] != "RELIABLE":
            continue
        comp = comp_index.get((p["segment_id"], p["change_category"], p["actor"]))
        if not (comp and comp["significant"]):
            continue
        decisive = p["degraded_ci_low"] > 0.5 or p["degraded_ci_high"] < 0.5
        worse = comp["direction"] == "higher"
        candidates.append({
            "segment": p["segment_id"], "change": f"{p['actor']}:{p['change_category']}",
            "n": p["n"], "accounts": p["n_accounts"],
            "degraded_rate": round(p["degraded_rate"], 3),
            "degraded_ci": (round(p["degraded_ci_low"], 3), round(p["degraded_ci_high"], 3)),
            "vs_rest_delta": round(comp["rate_delta"], 3),
            "p_value": round(comp["p_value"], 4),
            "direction": comp["direction"],
            "decisive_majority": decisive,
            "claim": (f"In {p['segment_id']}, {p['actor']} {p['change_category']} changes "
                      f"degrade {p['degraded_rate']*100:.0f}% of the time "
                      f"(95% CI {p['degraded_ci_low']*100:.0f}–{p['degraded_ci_high']*100:.0f}%), "
                      f"{abs(comp['rate_delta'])*100:.0f}pp {comp['direction']} than the rest "
                      f"of the population (p={comp['p_value']:.3f}) — "
                      f"{'scrutinize harder' if worse else 'relatively safe'} in this segment."),
        })
    # Worse-than-baseline first (more actionable), then by effect size.
    return sorted(candidates, key=lambda c: (c["direction"] != "higher", -abs(c["vs_rest_delta"])))


# ── Orchestration ──

def run_segments(db: Database, min_n: int = DIRECTIONAL_N) -> dict[str, Any]:
    """Full Phase 3 pass. Returns a summary dict; persists segments,
    segment_patterns, segment_comparisons."""
    eps = _clean_episodes(db)
    segments = enumerate_segments(db, eps)
    patterns = compute_segment_patterns(db, eps, min_n=min_n)
    comparisons = compare_segments(db, eps, min_n=min_n)
    db.execute("CHECKPOINT")
    cards = pattern_cards(patterns, comparisons)
    candidates = promotion_candidates(patterns, comparisons)
    return {
        "clean_episodes": len(eps),
        "segments": segments,
        "patterns": patterns,
        "comparisons": comparisons,
        "cards": cards,
        "promotion_candidates": candidates,
    }
