"""Phase 6.75 Fix — Action Magnitude Conditioning.

The per-metric weakness (6.75: every metric 22-62pp MAE) traced to templates
conditioning on action CATEGORY but not MAGNITUDE — a 'budget' template lumped
+300% and -91% cost changes together. This module extracts the change amount from
change_event old/new values, buckets it, and re-extracts templates with magnitude
as a required condition. The decisive test: does cost MAE drop below 15pp on
budget magnitude-conditioned templates? (the spec's mechanical-predictability claim)

Kept LOCAL to this module (not mutating templates._LEVELS) so the proven Phase 4/5
catalog is untouched; magnitude-aware templates are a parallel library that 6.75-fix
scores and Phase 7 consumes.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import permetric

_AMOUNT = re.compile(r"amount_micros:\s*(\d+)")
_TROAS = re.compile(r"target_roas:\s*([\d.]+)")
_TCPA = re.compile(r"target_cpa_micros:\s*(\d+)")


def _num(pat, s):
    m = pat.search(s or "")
    return float(m.group(1)) if m else None


# ── 6.75.1 extraction + 6.75.2 buckets ──

def _pct_bucket(pct: float) -> str:
    if pct < -0.30: return "large_decrease"
    if pct < -0.10: return "medium_decrease"
    if pct < -0.02: return "small_decrease"
    if pct <= 0.02: return "flat"
    if pct <= 0.10: return "small_increase"
    if pct <= 0.30: return "medium_increase"
    return "large_increase"


def _batch_bucket(count: int) -> str:
    if count <= 5: return "small_batch"
    if count <= 20: return "medium_batch"
    return "large_batch"


def extract_magnitude(category: str, old_value: str, new_value: str,
                      change_count: int) -> str:
    """Magnitude bucket for an episode. Budget/bid -> % buckets from old/new;
    keyword/creative -> batch buckets from change_count; else 'na'."""
    # budget
    o, n = _num(_AMOUNT, old_value), _num(_AMOUNT, new_value)
    if o and n and o > 0:
        return _pct_bucket((n - o) / o)
    # bid target (tROAS or tCPA)
    for pat in (_TROAS, _TCPA):
        o, n = _num(pat, old_value), _num(pat, new_value)
        if o and n and o > 0:
            return _pct_bucket((n - o) / o)
    # batch-size proxy for keyword / creative bundles
    if category in ("targeting_keyword", "asset", "ad_creative"):
        return _batch_bucket(change_count or 1)
    return "na"


def attach_magnitude(db: Database, episodes: list[dict]) -> list[dict]:
    """Add magnitude_bucket to each episode dict (via its representative change_event)."""
    ov = dict(((r[0],), (r[1], r[2])) for r in db.fetchall("""
        SELECT e.episode_id, ce.old_value, ce.new_value
        FROM episodes e JOIN change_events ce
          ON ce.account_id=e.account_id AND ce.change_id=e.change_event_id"""))
    for e in episodes:
        old, new = ov.get((e["episode_id"],), ("", ""))
        e["magnitude_bucket"] = extract_magnitude(
            e["change_category"], old, new, e.get("change_count", 1))
    return episodes


# ── 6.75.3 magnitude-aware extraction (cascade keeps magnitude) ──

_MAG_LEVELS = [
    ("change_category", "magnitude_bucket", "is_multi_action", "business_type", "vertical", "spend_tier", "pre_state"),
    ("change_category", "magnitude_bucket", "is_multi_action", "business_type", "vertical", "pre_state"),
    ("change_category", "magnitude_bucket", "is_multi_action", "business_type", "pre_state"),
    ("change_category", "magnitude_bucket", "is_multi_action", "pre_state"),
]


def _mag_id(cond: dict) -> str:
    parts = [cond["change_category"], f"mag={cond['magnitude_bucket']}",
             "multi" if cond.get("is_multi_action") else "single"]
    for k in ("business_type", "vertical", "spend_tier", "pre_state"):
        if k in cond:
            parts.append(str(cond[k]))
    return "__".join(parts)


def assign_mag_templates(eps: list[dict]) -> dict:
    """Each episode -> sharpest magnitude-aware template clearing the floors."""
    remaining = list(eps)
    assigned: dict[str, list] = {}
    for keys in _MAG_LEVELS:
        groups: dict[tuple, list] = defaultdict(list)
        for e in remaining:
            groups[tuple(e[k] for k in keys)].append(e)
        nxt = []
        for key, members in groups.items():
            accts = {m["account_id"] for m in members}
            if len(members) >= T.MIN_EPISODES and len(accts) >= T.MIN_ACCOUNTS:
                cond = dict(zip(keys, key))
                assigned[_mag_id(cond)] = members
            else:
                nxt.extend(members)
        remaining = nxt
    return assigned


# ── 6.75.4 per-metric scoring on magnitude-aware templates ──

def per_metric_mag(db: Database, episodes: list[dict] | None = None) -> dict:
    """Per-metric median/IQR/MAE for magnitude-aware templates; persist with a
    'mag:' prefix so they coexist with the category-only per_metric rows."""
    eps = episodes if episodes is not None else attach_magnitude(db, permetric._episodes_with_deltas(db))
    if "deltas" not in eps[0]:
        eps = attach_magnitude(db, permetric._episodes_with_deltas(db))
    assigned = assign_mag_templates(eps)
    db.execute("DELETE FROM per_metric_predictions WHERE template_id LIKE 'mag:%'")
    out = {}
    for tid, members in assigned.items():
        mt = {}
        for metric in permetric.METRICS:
            vals = [m["deltas"][metric] for m in members if m["deltas"].get(metric) is not None]
            if len(vals) < T.MIN_EPISODES:
                continue
            mae = permetric._kfold_metric_mae(members, metric)
            mt[metric] = {"median": statistics.median(vals),
                          "iqr_low": permetric._pct(vals, 0.25),
                          "iqr_high": permetric._pct(vals, 0.75), "mae": mae, "n": len(vals)}
            db.execute("""INSERT OR REPLACE INTO per_metric_predictions
                (template_id, metric, median_delta, iqr_low, iqr_high, mae, n)
                VALUES (?,?,?,?,?,?,?)""",
                ["mag:" + tid, metric, float(mt[metric]["median"]), float(mt[metric]["iqr_low"]),
                 float(mt[metric]["iqr_high"]), float(mae), len(vals)])
        out[tid] = mt
    db.execute("CHECKPOINT")
    return out


def predictability_ranking_mag(eps: list[dict]) -> list[dict]:
    """Per-metric MAE across magnitude-aware templates (the 6.75-fix re-score)."""
    assigned = assign_mag_templates(eps)
    err: dict[str, list] = defaultdict(list)
    for members in assigned.values():
        for metric in permetric.METRICS:
            vals = [(m, m["deltas"][metric]) for m in members if m["deltas"].get(metric) is not None]
            n = len(vals)
            if n < T.MIN_EPISODES:
                continue
            k = min(T.KFOLDS, n)
            folds = [vals[i::k] for i in range(k)]
            for i in range(k):
                test = folds[i]; train = [v for j, f in enumerate(folds) if j != i for v in f]
                if not train or not test:
                    continue
                pred = statistics.median([v for _, v in train])
                err[metric].extend(abs(pred - v) for _, v in test)
    rank = []
    for metric in permetric.METRICS:
        e = err.get(metric, [])
        if not e:
            continue
        good = sum(1 for x in e if x <= 0.10) / len(e)
        mae = sum(e) / len(e)
        rank.append({"metric": metric, "mae": mae, "exact_close_pct": good, "n": len(e),
                     "tier": "STRONG" if mae < 0.10 else "MODERATE" if mae < 0.15 else "WEAK"})
    return sorted(rank, key=lambda r: r["mae"])


def cost_mae_budget(eps: list[dict]) -> dict:
    """THE LOCK-IN TEST: cost-metric MAE restricted to budget magnitude-conditioned
    templates. Compares category-only vs magnitude-conditioned for budget episodes."""
    budget = [e for e in eps if e["change_category"] == "budget"]
    # magnitude-conditioned
    assigned = assign_mag_templates(budget)
    mag_err = []
    for members in assigned.values():
        vals = [(m, m["deltas"]["cost"]) for m in members if m["deltas"].get("cost") is not None]
        if len(vals) < T.MIN_EPISODES:
            continue
        k = min(T.KFOLDS, len(vals)); folds = [vals[i::k] for i in range(k)]
        for i in range(k):
            test = folds[i]; train = [v for j, f in enumerate(folds) if j != i for v in f]
            if not train or not test:
                continue
            pred = statistics.median([v for _, v in train])
            mag_err.extend(abs(pred - v) for _, v in test)
    # category-only baseline (all budget episodes, one group by state)
    by_state: dict[str, list] = defaultdict(list)
    for e in budget:
        if e["deltas"].get("cost") is not None:
            by_state[e["pre_state"]].append(e["deltas"]["cost"])
    cat_err = []
    for vals in by_state.values():
        if len(vals) < T.MIN_EPISODES:
            continue
        k = min(T.KFOLDS, len(vals)); folds = [vals[i::k] for i in range(k)]
        for i in range(k):
            test = folds[i]; train = [v for j, f in enumerate(folds) if j != i for v in f]
            if not train or not test:
                continue
            pred = statistics.median(train)
            cat_err.extend(abs(pred - v) for v in test)
    return {
        "magnitude_cost_mae": (sum(mag_err) / len(mag_err)) if mag_err else None,
        "magnitude_n": len(mag_err),
        "category_cost_mae": (sum(cat_err) / len(cat_err)) if cat_err else None,
        "category_n": len(cat_err),
        "passes_15pp": bool(mag_err and (sum(mag_err) / len(mag_err)) < 0.15),
    }
