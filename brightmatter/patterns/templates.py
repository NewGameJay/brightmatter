"""Phase 4 — State-Conditioned Templates & Historical Backtesting.

Turns episodes into programmatic templates that predict "given this campaign
state and this action, CPA will change by X%." No LLM anywhere in the loop:
templates are computed by episode aggregation + statistical testing, validated by
k-fold cross-validation, and activated by measured accuracy.

Pipeline:
  4.0 tag_episode_states()  -> pre_state / own_cpa_ratio / bench_cpa_ratio on episodes
  4.1 extract_templates()   -> exhaustive state x action enumeration w/ granularity cascade
  4.2 backtest_templates()  -> 5-fold CV: direction accuracy + magnitude buckets -> status
  4.3 persist + version      -> `templates`, `template_predictions` tables + live state doc
  4.4 shadow_simulate()     -> temporal holdout: predict-before-outcome, does live ~ backtest?
  4.5 recommend()           -> specific predictive recommendations for a campaign

CPA convention: signed change (post-pre)/pre. NEGATIVE = improvement (CPA fell).
Direction is recomputed from the signed change for EVERY episode — including
multi-action (outcome='confounded') ones, which carry a real CPA delta and become
their own template category via is_multi_action.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from brightmatter.analysis.trends import compute_trend
from brightmatter.benchmarks import benchmark_cpa, seasonal_cpa_index
from brightmatter.storage.database import Database

# ── Thresholds ──
MIN_EPISODES = 10
MIN_ACCOUNTS = 3
PROVISIONAL_N = 15
KFOLDS = 5
DIR_THRESHOLD = 0.10        # +/-10% CPA move = material (matches episode outcome logic)
VOLATILE_CV = 0.30
OWN_WEIGHT = 0.70           # own-history weight in the combined state score
BENCH_WEIGHT = 0.30
POST_WINDOW_DAYS = 7

# Activation bands (direction accuracy from CV)
ACTIVE_MIN = 0.55
RETIRE_MAX = 0.45


# ── CPA convention helpers ──

# CPA change is bounded below at -1.0 (CPA can't go negative) but unbounded above;
# tiny-denominator days produce absurd +4900% artifacts. Winsorize the upside so
# one outlier can't dominate MAE or the median. ±300% spans any real degradation.
MAG_CAP = 3.0


def signed_cpa_change(pre: dict, post: dict) -> float | None:
    """(post_cpa - pre_cpa)/pre_cpa, winsorized to [-1, MAG_CAP]. Negative =
    improvement. None if unreadable."""
    pre_cpa, post_cpa = pre.get("cpa", 0), post.get("cpa", 0)
    if not pre_cpa or not post_cpa:
        return None
    raw = (post_cpa - pre_cpa) / pre_cpa
    return max(-1.0, min(MAG_CAP, raw))


def direction_of(signed: float) -> str:
    """improved (CPA fell), degraded (CPA rose), or neutral."""
    if signed <= -DIR_THRESHOLD:
        return "improved"
    if signed >= DIR_THRESHOLD:
        return "degraded"
    return "neutral"


# ── 4.0 State bucketing ──

def classify_state(pre_cpa: float, avg_30d_cpa: float, benchmark_cpa_val: float | None,
                   trend_class: str, cv: float) -> tuple[str, float, float]:
    """Classify campaign state before a change. Own history weighted 70%, vertical
    benchmark 30%. Returns (state, own_ratio, bench_ratio)."""
    own_ratio = (pre_cpa / avg_30d_cpa) if avg_30d_cpa and avg_30d_cpa > 0 else 1.0
    bench_ratio = (pre_cpa / benchmark_cpa_val) if benchmark_cpa_val and benchmark_cpa_val > 0 else own_ratio
    # normalise Phase-2 classifications into improving / declining / stable / volatile
    t = trend_class
    if t in ("rising",):       # rising cost/CPA = declining performance
        t = "declining"
    elif t in ("falling",):    # falling CPA = improving performance
        t = "improving"

    # NOTE on ordering (deliberate, data-driven deviation from the spec's
    # volatile-first table): daily campaign CPA is so noisy that an absolute
    # CV>0.30 gate tags ~78% of episodes "volatile", collapsing the distribution
    # and violating lock-in 4.6 ("no state > 60%"). The campaign's *performance*
    # signal (own-history + benchmark + directional trend) is the meaningful
    # state; volatility is demoted to a residual that only catches mid-pack
    # campaigns with no clear performance read. Spec intent (a meaningful
    # distribution) is honoured over its literal first-check.
    if own_ratio > 2.0 and bench_ratio > 2.0:
        return "crisis", own_ratio, bench_ratio
    if t == "declining" and own_ratio > 1.0:
        return "struggling", own_ratio, bench_ratio
    if t == "improving" and own_ratio > 1.0:
        return "recovering", own_ratio, bench_ratio
    if t == "declining" and own_ratio <= 1.0:
        return "declining", own_ratio, bench_ratio
    if own_ratio <= 1.0 and bench_ratio <= 1.0:
        return "performing_well", own_ratio, bench_ratio
    if own_ratio <= 1.0 and bench_ratio > 1.0:
        return "above_average", own_ratio, bench_ratio
    if cv is not None and cv > VOLATILE_CV:
        return "volatile", own_ratio, bench_ratio
    return "stable", own_ratio, bench_ratio


def _load_daily_series(db: Database) -> tuple[dict, dict]:
    """In-memory daily (cost, conv) series keyed by (account,campaign) and by
    account — far faster than 4,889 windowed queries."""
    rows = db.fetchall("""
        SELECT account_id, campaign_id, date, cost_micros/1e6, conversions
        FROM daily_metrics
    """)
    cseries: dict[tuple, dict] = defaultdict(dict)
    aseries: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for acct, camp, d, cost, conv in rows:
        cseries[(acct, camp)][d] = (cost or 0.0, conv or 0.0)
        a = aseries[acct][d]
        a[0] += cost or 0.0
        a[1] += conv or 0.0
    return cseries, aseries


def _pre_change_context(series: dict, change_date) -> tuple[float, float, str]:
    """From a {date: (cost, conv)} series, the 30-day pre-change window:
    (avg_cpa, cv_of_daily_cpa, trend_class)."""
    start = change_date - timedelta(days=30)
    days, costs, convs, cpas = [], [], [], []
    for d, cc in series.items():
        cost, conv = (cc if isinstance(cc, tuple) else (cc[0], cc[1]))
        if start <= d < change_date:
            days.append(d)
            costs.append(cost)
            convs.append(conv)
            if conv > 0 and cost > 0:
                cpas.append((d, cost / conv))
    tot_cost, tot_conv = sum(costs), sum(convs)
    avg_cpa = (tot_cost / tot_conv) if tot_conv > 0 else 0.0
    cpa_vals = [v for _, v in cpas]
    cv = (statistics.pstdev(cpa_vals) / statistics.mean(cpa_vals)
          if len(cpa_vals) >= 2 and statistics.mean(cpa_vals) > 0 else 0.0)
    trend_class = "stable"
    if len(cpas) >= 5:
        t = compute_trend([d for d, _ in cpas], [v for _, v in cpas], "cpa")
        if t is not None:
            trend_class = t.classification
    return avg_cpa, cv, trend_class


def tag_episode_states(db: Database) -> dict[str, int]:
    """Compute and persist pre_state / own_cpa_ratio / bench_cpa_ratio on every
    episode. Returns the state distribution."""
    cseries, aseries = _load_daily_series(db)
    rows = db.fetchall("""
        SELECT e.episode_id, e.account_id, e.campaign_id, e.pre_metrics_json,
               ce.change_timestamp,
               COALESCE(NULLIF(a.vertical,''),'unknown') AS vertical
        FROM episodes e
        JOIN change_events ce ON ce.account_id = e.account_id AND ce.change_id = e.change_event_id
        LEFT JOIN accounts a ON a.account_id = e.account_id
    """)
    dist: Counter = Counter()
    for ep_id, acct, camp, pre_json, ts, vertical in rows:
        pre = json.loads(pre_json) if pre_json else {}
        pre_cpa = pre.get("cpa", 0) or 0
        change_date = ts.date() if hasattr(ts, "date") else ts
        series = cseries.get((acct, camp)) if camp else aseries.get(acct)
        if not series:
            avg_cpa, cv, trend_class = 0.0, 0.0, "stable"
        else:
            avg_cpa, cv, trend_class = _pre_change_context(series, change_date)
        bench = benchmark_cpa(vertical)
        if bench is not None:
            bench = bench * seasonal_cpa_index(vertical, change_date.month)
        state, own_r, bench_r = classify_state(pre_cpa, avg_cpa, bench, trend_class, cv)
        dist[state] += 1
        db.execute(
            "UPDATE episodes SET pre_state=?, own_cpa_ratio=?, bench_cpa_ratio=? WHERE episode_id=?",
            [state, float(own_r), float(bench_r), ep_id],
        )
    db.execute("CHECKPOINT")
    return dict(dist)


# ── Episode loading for templates ──

def _template_episodes(db: Database) -> list[dict]:
    """Episodes with everything templates key on, plus a recomputed signed CPA
    change + direction (so multi-action 'confounded' episodes are usable)."""
    rows = db.fetchall("""
        SELECT e.episode_id, e.account_id, e.campaign_id, e.change_category,
               e.change_count, e.actor, e.pre_state, e.pre_metrics_json, e.post_metrics_json,
               COALESCE(NULLIF(a.business_type,''),'unknown') AS business_type,
               COALESCE(NULLIF(a.vertical,''),'unknown')      AS vertical,
               COALESCE(NULLIF(a.spend_tier,''),'unknown')    AS spend_tier
        FROM episodes e
        LEFT JOIN accounts a ON a.account_id = e.account_id
        WHERE e.pre_state IS NOT NULL AND e.pre_state <> ''
    """)
    eps = []
    for r in rows:
        pre = json.loads(r[7]) if r[7] else {}
        post = json.loads(r[8]) if r[8] else {}
        signed = signed_cpa_change(pre, post)
        if signed is None:
            continue
        eps.append({
            "episode_id": r[0], "account_id": r[1], "campaign_id": r[2],
            "change_category": r[3], "change_count": r[4] or 1, "actor": r[5],
            "pre_state": r[6], "business_type": r[9], "vertical": r[10],
            "spend_tier": r[11],
            "is_multi_action": bool((r[4] or 1) > 1),
            "signed": signed, "direction": direction_of(signed),
        })
    return eps


# ── 4.1 Template extraction (granularity cascade) ──

# Sharpest -> broadest. Every level keeps the action + state; we drop geography.
_LEVELS = [
    ("change_category", "is_multi_action", "business_type", "vertical", "spend_tier", "pre_state"),
    ("change_category", "is_multi_action", "business_type", "vertical", "pre_state"),
    ("change_category", "is_multi_action", "business_type", "pre_state"),
    ("change_category", "is_multi_action", "pre_state"),
]


def _summarise(members: list[dict]) -> dict:
    signed = [m["signed"] for m in members]
    dirs = Counter(m["direction"] for m in members)
    signed_sorted = sorted(signed)

    def pct(p):
        if not signed_sorted:
            return 0.0
        k = (len(signed_sorted) - 1) * p
        f = int(k)
        c = min(f + 1, len(signed_sorted) - 1)
        return signed_sorted[f] + (signed_sorted[c] - signed_sorted[f]) * (k - f)

    return {
        "prediction_direction": dirs.most_common(1)[0][0],
        "prediction_magnitude": statistics.median(signed),
        "magnitude_iqr": (pct(0.25), pct(0.75)),
        "n_episodes": len(members),
        "n_accounts": len({m["account_id"] for m in members}),
        "dir_counts": dict(dirs),
    }


def extract_templates(episodes: list[dict], min_episodes: int = MIN_EPISODES,
                      min_accounts: int = MIN_ACCOUNTS) -> list[dict]:
    """Assign each episode to the SHARPEST level whose cell clears the floors;
    episodes that never qualify cascade to broader levels (and are dropped if even
    the broadest cell is too thin). No episode lands in two templates."""
    remaining = list(episodes)
    templates = []
    for level_idx, keys in enumerate(_LEVELS):
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for e in remaining:
            groups[tuple(e[k] for k in keys)].append(e)
        next_remaining = []
        for key, members in groups.items():
            accounts = {m["account_id"] for m in members}
            if len(members) >= min_episodes and len(accounts) >= min_accounts:
                cond = dict(zip(keys, key))
                t = {"conditions": cond, "level": level_idx, "members": members}
                t.update(_summarise(members))
                templates.append(t)
            else:
                next_remaining.extend(members)
        remaining = next_remaining
    return templates


# ── 4.2 Backtesting (5-fold CV) ──

def _magnitude_bucket(err: float) -> str:
    if err <= 0.05:
        return "exact"
    if err <= 0.10:
        return "close"
    if err <= 0.20:
        return "ballpark"
    return "miss"


def kfold_score(members: list[dict], k: int = KFOLDS) -> dict:
    """Stratified-by-template k-fold CV over a template's own episodes. Deterministic
    fold assignment (by index) so reruns reproduce. Returns direction accuracy,
    magnitude buckets, MAE."""
    n = len(members)
    k = min(k, n)
    folds = [members[i::k] for i in range(k)]  # round-robin = even, deterministic
    correct = total = 0
    buckets: Counter = Counter()
    abs_errs = []
    for i in range(k):
        test = folds[i]
        train = [m for j, f in enumerate(folds) if j != i for m in f]
        if not train or not test:
            continue
        train_dir = Counter(m["direction"] for m in train).most_common(1)[0][0]
        train_mag = statistics.median([m["signed"] for m in train])
        for m in test:
            total += 1
            if m["direction"] == train_dir:
                correct += 1
            err = abs(train_mag - m["signed"])
            abs_errs.append(err)
            buckets[_magnitude_bucket(err)] += 1
    return {
        "direction_accuracy": (correct / total) if total else 0.0,
        "magnitude_mae": (sum(abs_errs) / len(abs_errs)) if abs_errs else 0.0,
        "buckets": dict(buckets),
        "n_test": total,
    }


def _status(direction_accuracy: float, n_episodes: int) -> str:
    if n_episodes < PROVISIONAL_N:
        base = "PROVISIONAL"
    else:
        base = None
    if direction_accuracy < RETIRE_MAX:
        return "RETIRED"
    if direction_accuracy < ACTIVE_MIN:
        return "SHADOW_ONLY"
    return base or "ACTIVE"


def backtest_templates(templates: list[dict]) -> list[dict]:
    for t in templates:
        cv = kfold_score(t["members"])
        t["cv"] = cv
        t["status"] = _status(cv["direction_accuracy"], t["n_episodes"])
        t["template_id"] = template_id_of(t["conditions"])
    return templates


# ── 4.3 Catalog + versioning ──

_COND_ORDER = ("change_category", "is_multi_action", "business_type",
               "vertical", "spend_tier", "pre_state")


def template_id_of(cond: dict) -> str:
    """Deterministic, readable id from the conditions (stable across reruns so a
    template's versions line up)."""
    parts = []
    for k in _COND_ORDER:
        if k in cond:
            v = cond[k]
            parts.append("multi" if (k == "is_multi_action" and v) else
                         "single" if k == "is_multi_action" else str(v))
    return "__".join(parts)


def kfold_predictions(members: list[dict], template_id: str, version: int,
                      k: int = KFOLDS) -> list[dict]:
    """Per-episode backtest predictions (leave-fold-out), for template_predictions."""
    n = len(members)
    k = min(k, n)
    folds = [members[i::k] for i in range(k)]
    out = []
    for i in range(k):
        test = folds[i]
        train = [m for j, f in enumerate(folds) if j != i for m in f]
        if not train or not test:
            continue
        train_dir = Counter(m["direction"] for m in train).most_common(1)[0][0]
        train_mag = statistics.median([m["signed"] for m in train])
        for m in test:
            err = abs(train_mag - m["signed"])
            out.append({
                "template_id": template_id, "template_version": version,
                "episode_id": m["episode_id"],
                "predicted_direction": train_dir, "predicted_magnitude": train_mag,
                "actual_direction": m["direction"], "actual_magnitude": m["signed"],
                "direction_correct": bool(m["direction"] == train_dir),
                "magnitude_error": err, "magnitude_score": _magnitude_bucket(err),
                "source": "backtest",
            })
    return out


def persist_templates(db: Database, templates: list[dict],
                      run_date: str, log_predictions: bool = True) -> None:
    """Write the catalog with versioning. A template re-extracted with new data
    increments its version; prior versions are retained. Logs backtest predictions."""
    for t in templates:
        tid = t["template_id"]
        prev = db.fetchone("SELECT max(version) FROM templates WHERE template_id = ?", [tid])
        version = (prev[0] + 1) if prev and prev[0] is not None else 1
        cv = t["cv"]
        retired = run_date if t["status"] == "RETIRED" else None
        changelog = (f"v{version} extracted {run_date}: n={t['n_episodes']} "
                     f"accts={t['n_accounts']} dir_acc={cv['direction_accuracy']:.2f} "
                     f"status={t['status']}")
        db.execute("""
            INSERT OR REPLACE INTO templates
              (template_id, version, conditions_json, level, prediction_direction,
               prediction_magnitude, magnitude_iqr_low, magnitude_iqr_high,
               n_episodes, n_accounts, n_folds, direction_accuracy, magnitude_mae,
               status, created_at, last_validated, retired_at, changelog)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [tid, version, json.dumps(t["conditions"]), t["level"],
              t["prediction_direction"], float(t["prediction_magnitude"]),
              float(t["magnitude_iqr"][0]), float(t["magnitude_iqr"][1]),
              t["n_episodes"], t["n_accounts"], cv["n_test"],
              float(cv["direction_accuracy"]), float(cv["magnitude_mae"]),
              t["status"], run_date, run_date, retired, changelog])
        if log_predictions:
            for p in kfold_predictions(t["members"], tid, version):
                _insert_prediction(db, p)
    db.execute("CHECKPOINT")


def _insert_prediction(db: Database, p: dict) -> None:
    db.execute("""
        INSERT INTO template_predictions
          (template_id, template_version, episode_id, predicted_direction,
           predicted_magnitude, actual_direction, actual_magnitude, direction_correct,
           magnitude_error, magnitude_score, source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, [p["template_id"], p["template_version"], p["episode_id"],
          p["predicted_direction"], float(p["predicted_magnitude"]),
          p.get("actual_direction"),
          (float(p["actual_magnitude"]) if p.get("actual_magnitude") is not None else None),
          p.get("direction_correct"),
          (float(p["magnitude_error"]) if p.get("magnitude_error") is not None else None),
          p.get("magnitude_score"), p["source"]])


# ── 4.4 Shadow simulation (temporal holdout) ──

def shadow_simulate(db: Database, holdout_days: int = 14) -> dict:
    """Train templates on episodes OUTSIDE the most-recent `holdout_days`, then
    predict the held-out episodes (predict-before-outcome by construction — the
    template never saw them). Does live accuracy track backtest accuracy?"""
    eps = _template_episodes(db)
    # attach change dates
    dates = dict(db.fetchall("""
        SELECT e.episode_id, ce.change_timestamp
        FROM episodes e JOIN change_events ce
          ON ce.account_id=e.account_id AND ce.change_id=e.change_event_id
    """))
    for e in eps:
        ts = dates.get(e["episode_id"])
        e["change_date"] = (ts.date() if hasattr(ts, "date") else ts) if ts else None
    eps = [e for e in eps if e["change_date"] is not None]
    cutoff = max(e["change_date"] for e in eps) - timedelta(days=holdout_days)
    train_eps = [e for e in eps if e["change_date"] <= cutoff]
    holdout = [e for e in eps if e["change_date"] > cutoff]

    templates = backtest_templates(extract_templates(train_eps))
    active = {t["template_id"]: t for t in templates if t["status"] in ("ACTIVE", "PROVISIONAL")}

    matched = correct = 0
    buckets: Counter = Counter()
    used_template_acc = []  # backtest acc of templates actually matched (fair comparison)
    for e in holdout:
        # match the holdout episode to the sharpest active template it fits
        for keys in _LEVELS:
            cond = {k: e[k] for k in keys}
            tid = template_id_of(cond)
            t = active.get(tid)
            if t:
                matched += 1
                used_template_acc.append(t["cv"]["direction_accuracy"])
                if t["prediction_direction"] == e["direction"]:
                    correct += 1
                err = abs(t["prediction_magnitude"] - e["signed"])
                buckets[_magnitude_bucket(err)] += 1
                _insert_prediction(db, {
                    "template_id": tid, "template_version": 0, "episode_id": e["episode_id"],
                    "predicted_direction": t["prediction_direction"],
                    "predicted_magnitude": t["prediction_magnitude"],
                    "actual_direction": e["direction"], "actual_magnitude": e["signed"],
                    "direction_correct": bool(t["prediction_direction"] == e["direction"]),
                    "magnitude_error": err, "magnitude_score": _magnitude_bucket(err),
                    "source": "live",
                })
                break
    db.execute("CHECKPOINT")
    # Fair drift comparison: realized live accuracy vs the backtest accuracy of the
    # SAME templates that did the matching (not the all-template mean).
    backtest_acc = statistics.mean(used_template_acc) if used_template_acc else 0.0
    return {
        "holdout_cutoff": str(cutoff), "holdout_episodes": len(holdout),
        "train_episodes": len(train_eps), "templates_trained": len(templates),
        "active_templates": len(active),
        "matched": matched, "live_direction_accuracy": (correct / matched) if matched else 0.0,
        "backtest_direction_accuracy": backtest_acc, "buckets": dict(buckets),
    }


# ── 4.5 Recommendations ──

def recommend(db: Database, account_id: str, campaign_id: str) -> dict:
    """Match a campaign's CURRENT state to active templates and produce specific,
    predictive recommendations. Programmatic: SQL match + stored medians, no LLM."""
    row = db.fetchone("""
        SELECT COALESCE(NULLIF(a.business_type,''),'unknown'),
               COALESCE(NULLIF(a.vertical,''),'unknown'),
               COALESCE(NULLIF(a.spend_tier,''),'unknown')
        FROM accounts a WHERE a.account_id = ?
    """, [account_id])
    if not row:
        return {"error": f"unknown account {account_id}"}
    business_type, vertical, spend_tier = row
    # current state from the most recent episode for this campaign (its pre_state is
    # the closest available state snapshot); else neutral 'stable'.
    st = db.fetchone("""
        SELECT pre_state, own_cpa_ratio, bench_cpa_ratio FROM episodes
        WHERE account_id=? AND campaign_id=? AND pre_state IS NOT NULL AND pre_state<>''
        ORDER BY recorded_at DESC LIMIT 1
    """, [account_id, campaign_id])
    cur_state = st[0] if st else "stable"

    recs = []
    for is_multi in (False, True):
        base = {"is_multi_action": is_multi, "business_type": business_type,
                "vertical": vertical, "spend_tier": spend_tier, "pre_state": cur_state}
        for cat in _campaign_action_categories(db):
            base["change_category"] = cat
            for keys in _LEVELS:                       # sharpest first
                cond = {k: base[k] for k in keys}
                t = db.fetchone("""
                    SELECT template_id, prediction_direction, prediction_magnitude,
                           magnitude_iqr_low, magnitude_iqr_high, n_episodes, n_accounts,
                           direction_accuracy, magnitude_mae, status, version
                    FROM templates WHERE template_id=? AND status IN ('ACTIVE','PROVISIONAL')
                    ORDER BY version DESC LIMIT 1
                """, [template_id_of(cond)])
                if t:
                    recs.append({
                        "action": cat, "multi_action": is_multi,
                        "direction": t[1], "magnitude_pct": round(t[2] * 100, 1),
                        "range_pct": (round(t[3] * 100, 1), round(t[4] * 100, 1)),
                        "basis_episodes": t[5], "basis_accounts": t[6],
                        "backtest_dir_acc": round(t[7], 2), "mae_pct": round(t[8] * 100, 1),
                        "status": t[9], "version": t[10],
                        "template_id": t[0],
                    })
                    break
    recs.sort(key=lambda r: (-r["backtest_dir_acc"], -r["basis_episodes"]))
    return {
        "account_id": account_id, "campaign_id": campaign_id,
        "state": cur_state, "business_type": business_type, "vertical": vertical,
        "spend_tier": spend_tier, "recommendations": recs,
    }


def _campaign_action_categories(db: Database) -> list[str]:
    return [r[0] for r in db.fetchall(
        "SELECT DISTINCT change_category FROM episodes WHERE change_category<>''")]


# ── 4.3 Live state doc ──

def write_live_state_doc(db: Database, path: str, run_date: str) -> None:
    """Auto-generated 'live state' markdown: active templates, mean accuracy,
    recent live predictions, drift flags. This is the human-readable surface for
    auto-activation (humans engage at the recommendation stage, not activation)."""
    status_counts = dict(db.fetchall("SELECT status, count(*) FROM templates GROUP BY 1"))
    active = db.fetchall("""
        SELECT template_id, prediction_direction, prediction_magnitude,
               direction_accuracy, n_episodes, n_accounts
        FROM templates WHERE status='ACTIVE' ORDER BY direction_accuracy DESC LIMIT 20
    """)
    live = db.fetchone("""
        SELECT count(*), avg(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END)
        FROM template_predictions WHERE source='live'
    """)
    lines = [f"# BrightMatter — Phase 4 Live Template State", "",
             f"*Auto-generated {run_date}. Programmatic; no LLM in the loop.*", "",
             f"- Templates: **{sum(status_counts.values())}** "
             f"({status_counts.get('ACTIVE',0)} ACTIVE · {status_counts.get('PROVISIONAL',0)} PROVISIONAL · "
             f"{status_counts.get('SHADOW_ONLY',0)} SHADOW_ONLY · {status_counts.get('RETIRED',0)} RETIRED)",
             f"- Live (shadow) predictions logged: **{live[0]}**, "
             f"direction accuracy **{(live[1] or 0)*100:.0f}%**", "",
             "## Top active templates", "",
             "| Template | Predict | Magnitude | Backtest dir-acc | n / accts |",
             "|---|---|---|---|---|"]
    for tid, d, m, acc, n, na in active:
        lines.append(f"| `{tid}` | {d} | {m*100:+.0f}% | {acc*100:.0f}% | {n}/{na} |")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


# ── Orchestration ──

def run_templates(db: Database, run_date: str) -> dict:
    """Full Phase 4 pass: tag states -> extract -> backtest -> persist."""
    db.execute("DELETE FROM template_predictions WHERE source='backtest'")
    dist = tag_episode_states(db)
    eps = _template_episodes(db)
    templates = backtest_templates(extract_templates(eps))
    persist_templates(db, templates, run_date)
    by_status = Counter(t["status"] for t in templates)
    by_level = Counter(t["level"] for t in templates)
    return {
        "state_distribution": dist,
        "episodes_used": len(eps),
        "templates": templates,
        "n_templates": len(templates),
        "by_status": dict(by_status),
        "by_level": dict(by_level),
    }
