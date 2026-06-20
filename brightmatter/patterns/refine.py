"""Phase 4.5 — From Obvious to Non-Obvious.

Four refinement layers on the Phase 4 templates, all purely programmatic:

  4.5.1 mean_reversion_control()  -> separate action effect from regression to the mean
  4.5.2 mine_exceptions()         -> conditional rules that break the general pattern
  4.5.3 transfer_test()           -> do templates predict accounts they never saw?
  4.5.4 magnitude_convergence()   -> does magnitude tighten as observations accumulate?

Reuses Phase 4 machinery (state bucketing, extraction, CV). Tables: baseline_observations,
template_exceptions, magnitude_convergence. New template columns: natural_magnitude,
action_attributable_magnitude.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from scipy.stats import fisher_exact

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T

POST = T.POST_WINDOW_DAYS  # 7
PRE = 7


# ── shared episode loader with extra dimensions ──

def _campaign_types(db: Database) -> dict:
    """(account,campaign) -> dominant campaign_type from daily_metrics."""
    rows = db.fetchall("""
        SELECT account_id, campaign_id, campaign_type, count(*) c
        FROM daily_metrics WHERE campaign_type IS NOT NULL AND campaign_type <> ''
        GROUP BY 1,2,3
    """)
    best: dict[tuple, tuple] = {}
    for acct, camp, ct, c in rows:
        k = (acct, camp)
        if k not in best or c > best[k][1]:
            best[k] = (ct, c)
    return {k: v[0] for k, v in best.items()}


def refine_episodes(db: Database) -> list[dict]:
    """Phase-4 template episodes + campaign_type / is_pmax / is_brand / change_date."""
    eps = T._template_episodes(db)
    ctypes = _campaign_types(db)
    names = dict(((r[0], r[1]), r[2]) for r in db.fetchall(
        "SELECT DISTINCT account_id, campaign_id, campaign_name FROM daily_metrics"))
    dates = dict(db.fetchall("""
        SELECT e.episode_id, ce.change_timestamp FROM episodes e
        JOIN change_events ce ON ce.account_id=e.account_id AND ce.change_id=e.change_event_id
    """))
    for e in eps:
        k = (e["account_id"], e["campaign_id"])
        ct = ctypes.get(k, "unknown")
        e["campaign_type"] = ct
        e["is_pmax"] = (ct == "PERFORMANCE_MAX")
        nm = (names.get(k) or "").lower()
        e["is_brand"] = ("brand" in nm)
        e["change_bucket"] = "multi" if e["change_count"] > 1 else "single"
        ts = dates.get(e["episode_id"])
        e["change_date"] = (ts.date() if hasattr(ts, "date") else ts) if ts else None
    return eps


# ── 4.5.1 Mean-reversion control ──

def build_no_action_baseline(db: Database, step_days: int = POST) -> list[dict]:
    """Slide NON-overlapping 7d→7d windows across each campaign; keep windows with
    NO change events, classify the start state, measure the natural CPA trajectory.
    These are the 'do nothing' counterfactuals. Persists baseline_observations."""
    cseries, _ = T._load_daily_series(db)
    # change dates per (account,campaign)
    chg: dict[tuple, list] = defaultdict(list)
    for acct, camp, ts in db.fetchall("""
        SELECT account_id, campaign_id, change_timestamp FROM change_events WHERE campaign_id <> ''
    """):
        chg[(acct, camp)].append(ts.date() if hasattr(ts, "date") else ts)
    verticals = dict(db.fetchall("""
        SELECT account_id, COALESCE(NULLIF(vertical,''),'unknown') FROM accounts
    """))

    db.execute("DELETE FROM baseline_observations")
    obs = []
    for (acct, camp), series in cseries.items():
        if not camp or len(series) < (PRE + POST):
            continue
        days = sorted(series.keys())
        dmin, dmax = days[0], days[-1]
        changes = sorted(chg.get((acct, camp), []))
        anchor = dmin + timedelta(days=PRE)
        last = dmax - timedelta(days=POST)
        vertical = verticals.get(acct, "unknown")
        while anchor <= last:
            wstart, wend = anchor - timedelta(days=PRE), anchor + timedelta(days=POST)
            # no change event anywhere in the [pre, post] window
            if any(wstart <= c < wend for c in changes):
                anchor += timedelta(days=step_days)
                continue
            pre = _window_cpa(series, wstart, anchor)
            post = _window_cpa(series, anchor, wend)
            if pre is None or post is None or pre <= 0:
                anchor += timedelta(days=step_days)
                continue
            avg_cpa, cv, trend = T._pre_change_context(series, anchor)
            bench = T.benchmark_cpa(vertical)
            if bench is not None:
                bench = bench * T.seasonal_cpa_index(vertical, anchor.month)
            state, own_r, bench_r = T.classify_state(pre, avg_cpa, bench, trend, cv)
            change_pct = max(-1.0, min(T.MAG_CAP, (post - pre) / pre))
            obs.append({"account_id": acct, "campaign_id": camp, "state": state,
                        "cpa_change": change_pct})
            db.execute("""INSERT INTO baseline_observations
                (account_id, campaign_id, state, window_start, window_end,
                 cpa_start, cpa_end, cpa_change_pct, had_action)
                VALUES (?,?,?,?,?,?,?,?, FALSE)""",
                [acct, camp, state, wstart, wend, pre, post, change_pct])
            anchor += timedelta(days=step_days)
    db.execute("CHECKPOINT")
    return obs


def _window_cpa(series: dict, start, end) -> float | None:
    cost = conv = 0.0
    for d, cc in series.items():
        if start <= d < end:
            cost += cc[0]
            conv += cc[1]
    return (cost / conv) if conv > 0 else None


def mean_reversion_control(db: Database, episodes: list[dict]) -> dict:
    """Compare action (episode) trajectories to no-action baselines per state, and
    write natural_magnitude / action_attributable_magnitude onto every template."""
    baseline = build_no_action_baseline(db)
    base_by_state: dict[str, list] = defaultdict(list)
    for o in baseline:
        base_by_state[o["state"]].append(o["cpa_change"])
    action_by_state: dict[str, list] = defaultdict(list)
    for e in episodes:
        action_by_state[e["pre_state"]].append(e["signed"])

    states = sorted(set(base_by_state) | set(action_by_state))
    summary = {}
    for st in states:
        a = action_by_state.get(st, [])
        b = base_by_state.get(st, [])
        summary[st] = {
            "action_median": (statistics.median(a) if a else None), "action_n": len(a),
            "natural_median": (statistics.median(b) if b else None), "natural_n": len(b),
            "action_attributable": ((statistics.median(a) - statistics.median(b))
                                    if a and b else None),
        }

    # annotate templates with their state's natural + attributable magnitude
    for tid, version, cond_json, pred_mag in db.fetchall(
            "SELECT template_id, version, conditions_json, prediction_magnitude FROM templates"):
        st = json.loads(cond_json).get("pre_state")
        nat = summary.get(st, {}).get("natural_median")
        attributable = (pred_mag - nat) if (nat is not None) else None
        db.execute("""UPDATE templates SET natural_magnitude=?, action_attributable_magnitude=?
                      WHERE template_id=? AND version=?""",
                   [(float(nat) if nat is not None else None),
                    (float(attributable) if attributable is not None else None),
                    tid, version])
    db.execute("CHECKPOINT")
    return summary


# ── 4.5.2 Conditional exception mining ──

_EXC_DIMENSIONS = ("campaign_type", "is_pmax", "is_brand", "vertical",
                   "spend_tier", "change_bucket", "actor")
EXC_MIN_CLUSTER = 10
EXC_MIN_ACCOUNTS = 3
EXC_ALPHA = 0.05


def mine_exceptions(db: Database, episodes: list[dict], top_n: int = 10) -> list[dict]:
    """For the top ACTIVE templates, find dimension-values over-represented among the
    prediction MISSES (Fisher's exact). A cluster of >=10 misses / >=3 accounts on one
    condition = a conditional exception. Persists template_exceptions."""
    # rebuild template membership keyed the same way Phase 4 does
    tmpl_rows = db.fetchall("""
        SELECT template_id, conditions_json, prediction_direction, level, direction_accuracy, n_episodes
        FROM templates WHERE status='ACTIVE' ORDER BY direction_accuracy DESC, n_episodes DESC
    """)
    by_id = {T.template_id_of(json.loads(c)): (tid, json.loads(c), pred, lvl)
             for tid, c, pred, lvl, _, _ in tmpl_rows}
    # group episodes to their sharpest template (same cascade assignment as extraction)
    assigned = _assign_to_templates(episodes)

    db.execute("DELETE FROM template_exceptions")
    found = []
    for tid, cond, pred, lvl in list(by_id.values())[:top_n]:
        members = assigned.get(tid, [])
        if not members:
            continue
        hits = [m for m in members if m["direction"] == pred]
        misses = [m for m in members if m["direction"] != pred]
        if len(misses) < 5:
            continue
        for dim in _EXC_DIMENSIONS:
            if dim in cond:           # already fixed by the template — skip
                continue
            values = {m[dim] for m in members}
            for val in values:
                m_in = sum(1 for m in misses if m[dim] == val)
                m_out = len(misses) - m_in
                h_in = sum(1 for m in hits if m[dim] == val)
                h_out = len(hits) - h_in
                if m_in < EXC_MIN_CLUSTER:
                    continue
                accts = len({m["account_id"] for m in misses if m[dim] == val})
                if accts < EXC_MIN_ACCOUNTS:
                    continue
                _, p = fisher_exact([[m_in, m_out], [h_in, h_out]], alternative="greater")
                if p >= EXC_ALPHA:
                    continue
                # the exception sub-population: members matching this value
                sub = [m for m in members if m[dim] == val]
                sub_dir = Counter(x["direction"] for x in sub).most_common(1)[0][0]
                sub_mag = statistics.median([x["signed"] for x in sub])
                rec = {
                    "template_id": tid, "exception_dim": dim, "exception_value": str(val),
                    "n_exception": len(sub), "n_accounts": accts,
                    "base_prediction": pred, "exception_direction": sub_dir,
                    "exception_magnitude": sub_mag, "p_value": float(p),
                    "flips": sub_dir != pred,
                }
                found.append(rec)
                db.execute("""INSERT INTO template_exceptions
                    (template_id, exception_dim, exception_value, n_exception, n_accounts,
                     base_prediction, exception_direction, exception_magnitude, p_value, flips)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [rec["template_id"], rec["exception_dim"], rec["exception_value"],
                     rec["n_exception"], rec["n_accounts"], rec["base_prediction"],
                     rec["exception_direction"], float(rec["exception_magnitude"]),
                     rec["p_value"], rec["flips"]])
    db.execute("CHECKPOINT")
    # most interesting first: direction-flipping exceptions, then biggest cluster
    return sorted(found, key=lambda r: (not r["flips"], -r["n_exception"]))


def _assign_to_templates(episodes: list[dict]) -> dict:
    """Replicate extraction's sharpest-qualifying-cell assignment, returning
    template_id -> members (so exception mining sees the same groupings)."""
    remaining = list(episodes)
    assigned: dict[str, list] = {}
    for keys in T._LEVELS:
        groups: dict[tuple, list] = defaultdict(list)
        for e in remaining:
            groups[tuple(e[k] for k in keys)].append(e)
        nxt = []
        for key, members in groups.items():
            accts = {m["account_id"] for m in members}
            if len(members) >= T.MIN_EPISODES and len(accts) >= T.MIN_ACCOUNTS:
                cond = dict(zip(keys, key))
                assigned[T.template_id_of(cond)] = members
            else:
                nxt.extend(members)
        remaining = nxt
    return assigned


# ── 4.5.3 Cross-account transfer ──

def transfer_test(db: Database, episodes: list[dict], min_episodes: int = 20) -> dict:
    """Leave-one-account-out: train templates excluding an account entirely, predict
    that account's episodes. Stricter than k-fold (no episodes from the test account
    in training). Reports transfer accuracy vs the in-sample backtest baseline."""
    by_acct: dict[str, list] = defaultdict(list)
    for e in episodes:
        by_acct[e["account_id"]].append(e)
    holdout_accts = [a for a, es in by_acct.items() if len(es) >= min_episodes]

    overall_correct = overall_total = 0
    by_vertical: dict[str, list] = defaultdict(list)
    by_biztype: dict[str, list] = defaultdict(list)
    per_account = []
    for acct in holdout_accts:
        train = [e for e in episodes if e["account_id"] != acct]
        test = by_acct[acct]
        templates = T.backtest_templates(T.extract_templates(train))
        active = {t["template_id"]: t for t in templates if t["status"] in ("ACTIVE", "PROVISIONAL")}
        c = tot = 0
        for e in test:
            for keys in T._LEVELS:
                tid = T.template_id_of({k: e[k] for k in keys})
                t = active.get(tid)
                if t:
                    tot += 1
                    ok = (t["prediction_direction"] == e["direction"])
                    c += int(ok)
                    by_vertical[e["vertical"]].append(ok)
                    by_biztype[e["business_type"]].append(ok)
                    break
        if tot:
            per_account.append({"account_id": acct, "matched": tot, "accuracy": c / tot})
            overall_correct += c
            overall_total += tot
    return {
        "holdout_accounts": len(holdout_accts),
        "matched_episodes": overall_total,
        "transfer_accuracy": (overall_correct / overall_total) if overall_total else 0.0,
        "by_vertical": {v: (sum(x) / len(x), len(x)) for v, x in by_vertical.items() if len(x) >= 10},
        "by_business_type": {b: (sum(x) / len(x), len(x)) for b, x in by_biztype.items() if len(x) >= 10},
        "worst_accounts": sorted([p for p in per_account if p["matched"] >= 5],
                                 key=lambda p: p["accuracy"])[:5],
    }


# ── 4.5.4 Magnitude convergence ──

def magnitude_convergence(db: Database, episodes: list[dict], top_n: int = 10,
                          alpha: float = 0.1) -> list[dict]:
    """Simulate the shadow loop on existing data: walk each ACTIVE template's episodes
    in change-date order, EMA-update the magnitude on direction-correct observations,
    track running MAE. Persists magnitude_convergence. Answers: does MAE shrink?"""
    assigned = _assign_to_templates(episodes)
    active_ids = [r[0] for r in db.fetchall(
        "SELECT template_id FROM templates WHERE status='ACTIVE' "
        "ORDER BY n_episodes DESC LIMIT ?", [top_n])]
    db.execute("DELETE FROM magnitude_convergence")
    out = []
    for tid in active_ids:
        members = [m for m in assigned.get(tid, []) if m.get("change_date")]
        members.sort(key=lambda m: m["change_date"])
        if len(members) < 8:
            continue
        pred_dir = Counter(m["direction"] for m in members).most_common(1)[0][0]
        est = statistics.median([m["signed"] for m in members[:3]])  # seed
        abs_errs = []
        curve = []
        for i, m in enumerate(members, 1):
            err = abs(est - m["signed"])
            abs_errs.append(err)
            running_mae = sum(abs_errs) / len(abs_errs)
            db.execute("""INSERT INTO magnitude_convergence
                (template_id, observation_number, predicted_magnitude, actual_magnitude,
                 running_estimate, running_mae)
                VALUES (?,?,?,?,?,?)""",
                [tid, i, float(est), float(m["signed"]), float(est), float(running_mae)])
            curve.append((i, running_mae))
            if m["direction"] == pred_dir:        # update only on correct-direction obs
                est = est * (1 - alpha) + m["signed"] * alpha
        first_mae = curve[min(4, len(curve) - 1)][1]
        last_mae = curve[-1][1]
        out.append({"template_id": tid, "n": len(members),
                    "early_mae": first_mae, "late_mae": last_mae,
                    "converging": last_mae < first_mae, "curve": curve})
    db.execute("CHECKPOINT")
    return out
