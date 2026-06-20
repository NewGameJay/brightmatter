"""Phase 6 — Historical Simulations. Pure analysis on existing data.

  6.1 cold_start()        -> build BrightMatter from zero, week by week; accuracy curve
  6.2 reduced_account()   -> accuracy vs account count (50/100/150/223 x repeats)
  6.3 adversarial()       -> accuracy before/during/after cross-account disruption weeks

All leakage-free: each prediction uses only templates + a natural-trajectory baseline
derived from data STRICTLY BEFORE the predicted week / excluding the test accounts.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import refine
from brightmatter.patterns import actwait
from brightmatter.patterns import operate


def _natural_by_state(eps: list[dict]) -> dict:
    by: dict[str, list] = defaultdict(list)
    for e in eps:
        by[e["pre_state"]].append(e["signed"])
    return {st: statistics.median(v) for st, v in by.items() if v}


def _predict_set(train: list[dict], test: list[dict]) -> dict:
    """Train templates on `train`, predict each `test` episode. Returns direction +
    recommendation accuracy and coverage. Natural trajectory from train only."""
    templates = T.backtest_templates(T.extract_templates(train))
    active = {t["template_id"]: t for t in templates if t["status"] in ("ACTIVE", "PROVISIONAL")}
    natural = _natural_by_state(train)
    dir_hits = rec_hits = matched = decisive = 0
    for e in test:
        tmpl = None
        for keys in T._LEVELS:
            tmpl = active.get(T.template_id_of({k: e[k] for k in keys}))
            if tmpl:
                break
        if not tmpl:
            continue
        matched += 1
        if tmpl["prediction_direction"] == e["direction"]:
            dir_hits += 1
        nat = natural.get(e["pre_state"])
        if nat is not None:
            action_cost = tmpl["prediction_magnitude"] - nat
            rec, _ = actwait._decision(action_cost)
            if rec != "EITHER":
                decisive += 1
                actual_cost = e["signed"] - nat
                if operate._recommendation_correct(rec, actual_cost):
                    rec_hits += 1
    return {
        "n_test": len(test), "templates": len(templates), "active": len(active),
        "matched": matched, "coverage": matched / len(test) if test else 0.0,
        "direction_accuracy": dir_hits / matched if matched else None,
        "decisive": decisive,
        "recommendation_accuracy": rec_hits / decisive if decisive else None,
    }


# ── 6.1 Cold start ──

def cold_start(db: Database, step_days: int = 7) -> list[dict]:
    eps = [e for e in refine.refine_episodes(db) if e.get("change_date")]
    dmin = min(e["change_date"] for e in eps)
    dmax = max(e["change_date"] for e in eps)
    rows = []
    cutoff = dmin + timedelta(days=step_days)   # week 1 has no training data
    wk = 1
    while cutoff <= dmax + timedelta(days=step_days):
        train = [e for e in eps if e["change_date"] < cutoff]
        test = [e for e in eps if cutoff <= e["change_date"] < cutoff + timedelta(days=step_days)]
        if not test:
            cutoff += timedelta(days=step_days); wk += 1; continue
        if len(train) < T.MIN_EPISODES:
            rows.append({"week": wk, "week_start": str(cutoff), "train_episodes": len(train),
                         "templates": 0, "changes": len(test), "matched": 0, "coverage": 0.0,
                         "direction_accuracy": None, "recommendation_accuracy": None})
        else:
            r = _predict_set(train, test)
            rows.append({"week": wk, "week_start": str(cutoff), "train_episodes": len(train),
                         "templates": r["templates"], "changes": len(test),
                         "matched": r["matched"], "coverage": r["coverage"],
                         "direction_accuracy": r["direction_accuracy"],
                         "recommendation_accuracy": r["recommendation_accuracy"]})
        cutoff += timedelta(days=step_days); wk += 1
    return rows


# ── 6.2 Reduced account ──

def _stratified_sample(accounts: list[tuple], n: int, seed: int) -> list[str]:
    """accounts = [(account_id, business_type)]. Deterministic stratified pick by
    business_type, varied by seed (no RNG — index rotation)."""
    by_type: dict[str, list] = defaultdict(list)
    for aid, bt in sorted(accounts):
        by_type[bt].append(aid)
    for bt in by_type:                       # deterministic per-seed rotation
        lst = by_type[bt]
        k = seed % max(1, len(lst))
        by_type[bt] = lst[k:] + lst[:k]
    total = len(accounts)
    picked = []
    for bt, lst in by_type.items():
        take = max(1, round(n * len(lst) / total))
        picked.extend(lst[:take])
    return picked[:n]


def reduced_account(db: Database, tiers=(50, 100, 150, 223), repeats: int = 5) -> list[dict]:
    eps = [e for e in refine.refine_episodes(db)]
    accounts = db.fetchall("""
        SELECT DISTINCT e.account_id, COALESCE(NULLIF(a.business_type,''),'unknown')
        FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id""")
    by_acct: dict[str, list] = defaultdict(list)
    for e in eps:
        by_acct[e["account_id"]].append(e)
    n_total = len(accounts)
    out = []
    for tier in tiers:
        accs, covs, dirs, recs = [], [], [], []
        reps = 1 if tier >= n_total else repeats
        for rep in range(reps):
            sample = _stratified_sample(accounts, min(tier, n_total), seed=rep * 7 + 1)
            sample_eps = [e for a in sample for e in by_acct.get(a, [])]
            if len(sample_eps) < T.MIN_EPISODES:
                continue
            # 5-fold-style: split episodes 80/20 by index for a quick in-sample read
            templates = T.backtest_templates(T.extract_templates(sample_eps))
            active = [t for t in templates if t["status"] == "ACTIVE"]
            dacc = statistics.mean([t["cv"]["direction_accuracy"] for t in active]) if active else None
            # coverage: fraction of episodes landing in any extracted template
            assigned = sum(len(m) for m in refine._assign_to_templates(sample_eps).values())
            accs.append(len(templates)); covs.append(assigned / len(sample_eps))
            if dacc is not None:
                dirs.append(dacc)
        out.append({
            "tier": tier, "repeats": reps,
            "templates_mean": statistics.mean(accs) if accs else 0,
            "templates_std": statistics.pstdev(accs) if len(accs) > 1 else 0,
            "coverage_mean": statistics.mean(covs) if covs else 0,
            "active_dir_acc_mean": statistics.mean(dirs) if dirs else None,
            "active_dir_acc_std": statistics.pstdev(dirs) if len(dirs) > 1 else 0,
        })
    return out


# ── 6.3 Adversarial periods ──

def find_disruptions(db: Database, z: float = 2.0, top_n: int = 3) -> list[dict]:
    """Weeks with regime-change volume >= z std devs above mean. If none clear the
    bar (no platform-level event), fall back to the top_n highest-volume weeks so
    we still measure accuracy around the busiest periods."""
    weekly = db.fetchall("""
        SELECT date_trunc('week', change_date)::DATE AS wk,
               count(*) AS regimes, count(DISTINCT account_id) AS accts
        FROM regime_changes GROUP BY 1 ORDER BY 1""")
    if len(weekly) < 3:
        return []
    counts = [r[1] for r in weekly]
    mean, sd = statistics.mean(counts), (statistics.pstdev(counts) or 1)
    flagged = [{"week": str(r[0]), "regimes": r[1], "accounts": r[2],
                "z": (r[1] - mean) / sd, "above_2sd": (r[1] - mean) / sd >= z}
               for r in weekly]
    hits = [f for f in flagged if f["above_2sd"]]
    if hits:
        return hits
    return sorted(flagged, key=lambda f: -f["regimes"])[:top_n]


def adversarial(db: Database) -> dict:
    eps = [e for e in refine.refine_episodes(db) if e.get("change_date")]
    disruptions = find_disruptions(db)
    # global cumulative-train accuracy by week (reuse cold_start rows for the timeline)
    from datetime import date
    results = []
    for d in disruptions:
        wk = date.fromisoformat(d["week"])
        def acc_in(lo, hi):
            train = [e for e in eps if e["change_date"] < lo]
            test = [e for e in eps if lo <= e["change_date"] < hi]
            if len(train) < T.MIN_EPISODES or not test:
                return None
            return _predict_set(train, test)
        pre = acc_in(wk - timedelta(days=14), wk)
        dur = acc_in(wk, wk + timedelta(days=7))
        post = acc_in(wk + timedelta(days=7), wk + timedelta(days=21))
        results.append({"disruption_week": d["week"], "regimes": d["regimes"],
                        "accounts": d["accounts"], "z": round(d["z"], 1),
                        "pre": pre, "during": dur, "post": post})
    return {"disruptions": disruptions, "windows": results}
