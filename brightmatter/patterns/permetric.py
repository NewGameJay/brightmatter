"""Phase 6.75 — Per-Metric Template Predictions.

Reshapes templates from a single composite outcome to per-metric predictions
(impressions +22%, CPA +9%, conversions +14%, ...) so the marketer sees the
trade-off, not a blended verdict — and so the system exposes WHICH metrics it can
actually predict.

  6.75.1 compute_metric_deltas()        -> % change per metric per episode
  6.75.2 per_metric_templates()         -> median/IQR/MAE per metric per template
  6.75.3 predictability_ranking()       -> which metrics are predictable (MAE, %exact+close)
  6.75.4 register/resolve metric hypotheses -> testable, self-adjusting per-metric predictions

Every metric delta is winsorized to [-1, +3] (tiny-denominator artifacts). ctr is
derived (clicks/impressions); impression_share isn't in episode metrics (noted).
"""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import refine

# Metrics carried in episode pre/post JSON, + derived ctr.
METRICS = ("impressions", "clicks", "cost", "conversions", "conversion_value",
           "cpa", "cvr", "ctr", "roas")
CAP = T.MAG_CAP


def _derived(m: dict) -> dict:
    d = dict(m)
    imp, clk = m.get("impressions") or 0, m.get("clicks") or 0
    d["ctr"] = (clk / imp) if imp else None
    return d


def compute_metric_deltas(pre: dict, post: dict) -> dict:
    """Signed % change per metric, winsorized. None where unreadable."""
    pre, post = _derived(pre), _derived(post)
    out = {}
    for metric in METRICS:
        pv, qv = pre.get(metric), post.get(metric)
        if pv and pv != 0 and qv is not None:
            out[metric] = max(-1.0, min(CAP, (qv - pv) / pv))
        else:
            out[metric] = None
    return out


def _episodes_with_deltas(db: Database) -> list[dict]:
    eps = refine.refine_episodes(db)
    import json
    rows = dict(db.fetchall("SELECT episode_id, pre_metrics_json FROM episodes"))
    post_rows = dict(db.fetchall("SELECT episode_id, post_metrics_json FROM episodes"))
    for e in eps:
        pre = json.loads(rows.get(e["episode_id"]) or "{}")
        post = json.loads(post_rows.get(e["episode_id"]) or "{}")
        e["deltas"] = compute_metric_deltas(pre, post)
    return eps


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = int(k); c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


# ── 6.75.2 Per-metric template reshaping ──

def per_metric_templates(db: Database, episodes: list[dict] | None = None) -> dict:
    """template_id -> {metric: {median, iqr_low, iqr_high, mae, n}}. MAE from per-metric
    k-fold on the template's own episodes. Persists per_metric_predictions."""
    eps = episodes if episodes is not None else _episodes_with_deltas(db)
    assigned = refine._assign_to_templates(eps)
    db.execute("DELETE FROM per_metric_predictions")
    out = {}
    for tid, members in assigned.items():
        mt = {}
        for metric in METRICS:
            vals = [m["deltas"][metric] for m in members if m["deltas"].get(metric) is not None]
            if len(vals) < T.MIN_EPISODES:
                continue
            mae = _kfold_metric_mae(members, metric)
            rec = {"median": statistics.median(vals),
                   "iqr_low": _pct(vals, 0.25), "iqr_high": _pct(vals, 0.75),
                   "mae": mae, "n": len(vals)}
            mt[metric] = rec
            db.execute("""INSERT OR REPLACE INTO per_metric_predictions
                (template_id, metric, median_delta, iqr_low, iqr_high, mae, n)
                VALUES (?,?,?,?,?,?,?)""",
                [tid, metric, float(rec["median"]), float(rec["iqr_low"]),
                 float(rec["iqr_high"]), float(mae), len(vals)])
        out[tid] = mt
    db.execute("CHECKPOINT")
    return out


def _kfold_metric_mae(members: list[dict], metric: str, k: int = T.KFOLDS) -> float:
    vals = [(m, m["deltas"][metric]) for m in members if m["deltas"].get(metric) is not None]
    n = len(vals)
    if n < 2:
        return 0.0
    k = min(k, n)
    folds = [vals[i::k] for i in range(k)]
    errs = []
    for i in range(k):
        test = folds[i]
        train = [v for j, f in enumerate(folds) if j != i for v in f]
        if not train or not test:
            continue
        pred = statistics.median([v for _, v in train])
        errs.extend(abs(pred - v) for _, v in test)
    return (sum(errs) / len(errs)) if errs else 0.0


# ── 6.75.3 Predictability ranking ──

def _bucket(err: float) -> str:
    if err <= 0.05: return "exact"
    if err <= 0.10: return "close"
    if err <= 0.20: return "ballpark"
    return "miss"


def predictability_ranking(db: Database, episodes: list[dict] | None = None) -> list[dict]:
    """Across all templates' k-fold holdout, per-metric MAE + bucket distribution.
    Answers: which metrics can BrightMatter actually predict?"""
    eps = episodes if episodes is not None else _episodes_with_deltas(db)
    assigned = refine._assign_to_templates(eps)
    per_metric_err: dict[str, list] = defaultdict(list)
    for members in assigned.values():
        for metric in METRICS:
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
                for _, v in test:
                    per_metric_err[metric].append(abs(pred - v))
    rank = []
    for metric in METRICS:
        errs = per_metric_err.get(metric, [])
        if not errs:
            continue
        buckets = [_bucket(e) for e in errs]
        good = sum(1 for b in buckets if b in ("exact", "close")) / len(buckets)
        mae = sum(errs) / len(errs)
        tier = "STRONG" if mae < 0.10 else "MODERATE" if mae < 0.15 else "WEAK"
        rank.append({"metric": metric, "mae": mae, "exact_close_pct": good,
                     "n": len(errs), "tier": tier})
    return sorted(rank, key=lambda r: r["mae"])


# ── 6.75.4 Metric-prediction hypothesis loop ──

def _mid(episode_id: str, template_id: str, metric: str) -> str:
    return hashlib.sha256(f"{episode_id}|{template_id}|{metric}".encode()).hexdigest()[:16]


def register_metric_hypotheses(db: Database, episodes: list[dict] | None = None) -> int:
    """For each episode matched to a template, register a per-metric prediction
    (median + IQR range) as a testable hypothesis. Idempotent."""
    eps = episodes if episodes is not None else _episodes_with_deltas(db)
    pmt = {tid: {r[0]: r[1:] for r in db.fetchall(
              "SELECT metric, median_delta, iqr_low, iqr_high FROM per_metric_predictions WHERE template_id=?", [tid])}
           for (tid,) in db.fetchall("SELECT DISTINCT template_id FROM per_metric_predictions")}
    assigned = refine._assign_to_templates(eps)
    ep_to_tid = {m["episode_id"]: tid for tid, members in assigned.items() for m in members}
    n = 0
    for e in eps:
        tid = ep_to_tid.get(e["episode_id"])
        if not tid or tid not in pmt:
            continue
        for metric, (median, lo, hi) in pmt[tid].items():
            pid = _mid(e["episode_id"], tid, metric)
            db.execute("""INSERT OR REPLACE INTO metric_predictions
                (prediction_id, episode_id, template_id, metric, predicted_median,
                 predicted_iqr_low, predicted_iqr_high, registered_at)
                VALUES (?,?,?,?,?,?,?, ?)""",
                [pid, e["episode_id"], tid, metric, median, lo, hi, e.get("change_date")])
            n += 1
    db.execute("CHECKPOINT")
    return n


def resolve_metric_hypotheses(db: Database, episodes: list[dict] | None = None) -> dict:
    """Score each registered metric prediction against the episode's actual delta.
    Records error + within-IQR. Accumulates per-(template,metric) accuracy."""
    eps = episodes if episodes is not None else _episodes_with_deltas(db)
    deltas = {e["episode_id"]: e["deltas"] for e in eps}
    rows = db.fetchall("""SELECT prediction_id, episode_id, metric, predicted_median,
                                 predicted_iqr_low, predicted_iqr_high FROM metric_predictions""")
    n = 0
    for pid, eid, metric, med, lo, hi in rows:
        actual = deltas.get(eid, {}).get(metric)
        if actual is None:
            continue
        err = abs(med - actual)
        within = (lo <= actual <= hi)
        db.execute("""UPDATE metric_predictions SET actual_delta=?, error=?, within_iqr=?,
                      resolved=TRUE WHERE prediction_id=?""",
                   [float(actual), float(err), bool(within), pid])
        n += 1
    db.execute("CHECKPOINT")
    # per-metric live accuracy summary
    summ = db.fetchall("""
        SELECT metric, count(*), avg(error),
               avg(CASE WHEN within_iqr THEN 1.0 ELSE 0.0 END)
        FROM metric_predictions WHERE resolved GROUP BY 1 ORDER BY 3""")
    return {"resolved": n,
            "by_metric": {r[0]: {"n": r[1], "mae": r[2], "within_iqr": r[3]} for r in summ}}


def recommendation_metric_forecast(db: Database, account_id: str, campaign_id: str) -> dict:
    """Per-metric forecast for a campaign's matched template — concrete numbers + ranges."""
    st = db.fetchone("""SELECT pre_state FROM episodes WHERE account_id=? AND campaign_id=?
                        AND pre_state IS NOT NULL AND pre_state<>'' ORDER BY recorded_at DESC LIMIT 1""",
                     [account_id, campaign_id])
    row = db.fetchone("""SELECT COALESCE(NULLIF(business_type,''),'unknown'),
                                COALESCE(NULLIF(vertical,''),'unknown'),
                                COALESCE(NULLIF(spend_tier,''),'unknown')
                         FROM accounts WHERE account_id=?""", [account_id])
    if not row or not st:
        return {}
    biz, vert, tier = row
    state = st[0]
    for cat in [r[0] for r in db.fetchall("SELECT DISTINCT change_category FROM episodes WHERE change_category<>''")]:
        for is_multi in (False, True):
            base = {"change_category": cat, "is_multi_action": is_multi, "business_type": biz,
                    "vertical": vert, "spend_tier": tier, "pre_state": state}
            for keys in T._LEVELS:
                tid = T.template_id_of({k: base[k] for k in keys})
                mp = db.fetchall("""SELECT metric, median_delta, iqr_low, iqr_high, mae, n
                                    FROM per_metric_predictions WHERE template_id=? ORDER BY mae""", [tid])
                if mp:
                    return {"template_id": tid, "state": state, "action": cat, "multi": is_multi,
                            "metrics": [{"metric": m, "median": md, "low": lo, "high": hi,
                                         "mae": mae, "n": n} for m, md, lo, hi, mae, n in mp]}
    return {}
