"""Phase 5 — Operationalization: the continuous act-vs-wait loop.

  5.1 register_predictions()    -> log a recommendation per new episode BEFORE its outcome
  5.2 resolve_predictions()     -> when a 7/14/30d window closes, score it (incl. the product metric)
  5.3 update_template_health()  -> rolling live accuracy, promote/demote/retire, drift flags
  5.5 generate_live_state()     -> the daily human-readable state doc

The product metric is RECOMMENDATION accuracy, not direction accuracy: was "wait /
don't-act / act / either" the right call, judged against the campaign's actual
post-change trajectory vs. the no-action baseline for its state.

Validated as a simulation over the historical panel: each episode is "registered"
at its change date and "resolved" at whatever windows have closed by the as-of
date — exactly the lagged-feedback structure of live operation.
"""

from __future__ import annotations

import hashlib
import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import refine
from brightmatter.patterns import actwait

WINDOWS = (7, 14, 30)
PRE = 7
DECISION_BAND = actwait.ACT_THRESHOLD       # 0.10
STRONG = actwait.STRONG_AVOID               # 0.20


def _pred_id(episode_id: str, template_id: str) -> str:
    return hashlib.sha256(f"{episode_id}|{template_id}".encode()).hexdigest()[:16]


def _data_max_date(db: Database):
    return db.fetchone("SELECT max(date) FROM daily_metrics")[0]


# ── 5.1 Registration ──

def register_predictions(db: Database, episodes: list[dict] | None = None) -> int:
    """For each episode, match the sharpest ACTIVE/PROVISIONAL template, compute the
    recommendation from (template prediction − natural trajectory), and log it. Pure
    pre-outcome: we never read the episode's realized magnitude here."""
    eps = episodes if episodes is not None else refine.refine_episodes(db)
    natural = actwait.natural_trajectory(db)

    # sharpest active template per condition tuple (cache by template_id)
    tmpl_cache: dict[str, tuple] = {}
    for tid, cj, pdir, pmag, attrib in db.fetchall(
            """SELECT template_id, conditions_json, prediction_direction,
                      prediction_magnitude, action_attributable_magnitude
               FROM templates WHERE status IN ('ACTIVE','PROVISIONAL')"""):
        tmpl_cache[tid] = (pdir, pmag, attrib)

    n = 0
    for e in eps:
        if e.get("change_date") is None:
            continue
        state = e["pre_state"]
        nat = natural.get(state)
        if nat is None:
            continue
        base = {"change_category": e["change_category"], "is_multi_action": e["is_multi_action"],
                "business_type": e["business_type"], "vertical": e["vertical"],
                "spend_tier": e["spend_tier"], "pre_state": state}
        tid = None
        for keys in T._LEVELS:
            cand = T.template_id_of({k: base[k] for k in keys})
            if cand in tmpl_cache:
                tid = cand
                break
        if tid is None:
            continue
        pdir, pmag, attrib = tmpl_cache[tid]
        action_cost = attrib if attrib is not None else (pmag - nat)
        rec, _ = actwait._decision(action_cost)
        pid = _pred_id(e["episode_id"], tid)
        db.execute("""INSERT OR REPLACE INTO live_predictions
            (prediction_id, template_id, episode_id, account_id, campaign_id, state,
             predicted_direction, predicted_magnitude, natural_magnitude,
             action_cost_predicted, recommendation, registered_at, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'live')""",
            [pid, tid, e["episode_id"], e["account_id"], e["campaign_id"], state,
             pdir, float(pmag), float(nat), float(action_cost), rec, e["change_date"]])
        n += 1
    db.execute("CHECKPOINT")
    return n


# ── 5.2 Resolution ──

def _post_window_change(series: dict, change_date, window: int):
    """Signed CPA change: post window [cd, cd+window) vs pre [cd-7, cd). Winsorized."""
    def cpa(start, end):
        cost = conv = 0.0
        for d, cc in series.items():
            if start <= d < end:
                cost += cc[0]; conv += cc[1]
        return (cost / conv) if conv > 0 else None
    pre = cpa(change_date - timedelta(days=PRE), change_date)
    post = cpa(change_date, change_date + timedelta(days=window))
    if pre is None or post is None or pre <= 0:
        return None
    return max(-1.0, min(T.MAG_CAP, (post - pre) / pre))


def _recommendation_correct(rec: str, actual_cost: float) -> bool:
    """actual_cost = actual CPA change − natural trajectory (positive = acting worse)."""
    helped = actual_cost < -DECISION_BAND
    hurt = actual_cost > DECISION_BAND
    if rec == "DO_NOT_ACT":
        return hurt                      # we warned; acting indeed hurt
    if rec == "ACT":
        return helped                    # we encouraged; acting indeed helped
    if rec == "EITHER":
        return (not helped) and (not hurt)
    return not helped                    # WAIT: correct unless acting clearly beat waiting


def resolve_predictions(db: Database, as_of=None) -> dict:
    """Resolve every (prediction, window) whose window has closed by as_of and isn't
    yet resolved, using actual post-window CPA from daily_metrics. Scores direction,
    magnitude, and the recommendation product metric."""
    as_of = as_of or _data_max_date(db)
    cseries, _ = T._load_daily_series(db)

    preds = db.fetchall("""SELECT prediction_id, account_id, campaign_id, state,
                                  predicted_direction, predicted_magnitude, natural_magnitude,
                                  recommendation, registered_at FROM live_predictions""")
    already = {(pid, w) for pid, w in db.fetchall(
        "SELECT prediction_id, window_days FROM prediction_resolutions")}
    n_new = 0
    for pid, acct, camp, state, pdir, pmag, nat, rec, reg in preds:
        series = cseries.get((acct, camp)) if camp else None
        if series is None:
            continue
        for w in WINDOWS:
            if (pid, w) in already:
                continue
            if reg + timedelta(days=w) > as_of:        # window not closed yet
                continue
            actual = _post_window_change(series, reg, w)
            if actual is None:
                continue
            actual_dir = T.direction_of(actual)
            dir_ok = (pdir == actual_dir)
            mag_err = abs(pmag - actual)
            actual_cost = actual - nat
            rec_ok = _recommendation_correct(rec, actual_cost)
            db.execute("""INSERT INTO prediction_resolutions
                (prediction_id, window_days, actual_magnitude, actual_direction,
                 direction_correct, magnitude_error, magnitude_score,
                 actual_action_cost, recommendation_correct)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                [pid, w, float(actual), actual_dir, dir_ok, float(mag_err),
                 T._magnitude_bucket(mag_err), float(actual_cost), rec_ok])
            n_new += 1
    db.execute("CHECKPOINT")
    return {"as_of": str(as_of), "newly_resolved": n_new}


# ── 5.3 Template health ──

def update_template_health(db: Database) -> dict:
    """Roll resolved predictions (14d window = the headline) into per-template live
    accuracy, set status, and flag drift vs. backtest."""
    rows = db.fetchall("""
        SELECT lp.template_id, r.direction_correct, r.recommendation_correct, r.magnitude_error
        FROM prediction_resolutions r JOIN live_predictions lp ON lp.prediction_id = r.prediction_id
        WHERE r.window_days = 14""")
    by_t: dict[str, list] = defaultdict(list)
    for tid, dok, rok, mae in rows:
        by_t[tid].append((dok, rok, mae))
    backtest = dict(db.fetchall("SELECT template_id, direction_accuracy FROM templates"))

    db.execute("DELETE FROM template_health")
    drift = promoted = demoted = 0
    for tid, recs in by_t.items():
        n = len(recs)
        dacc = sum(1 for r in recs if r[0]) / n
        racc = sum(1 for r in recs if r[1]) / n
        mae = sum(r[2] for r in recs) / n
        bt = backtest.get(tid, 0.0)
        flag = ""
        if n >= 10 and dacc < bt - 0.15:
            flag = "DRIFT"; drift += 1
        elif n >= 10 and dacc > bt + 0.05:
            flag = "IMPROVING"
        if n >= 10 and dacc > 0.55:
            status = "ACTIVE"; promoted += 1
        elif n < 10 or 0.45 <= dacc <= 0.55:
            status = "SHADOW_ONLY"
        else:
            status = "RETIRED"; demoted += 1
        db.execute("""INSERT INTO template_health
            (template_id, n_resolved, live_direction_accuracy, live_recommendation_accuracy,
             magnitude_mae, backtest_direction_accuracy, status, drift_flag, updated_at)
            VALUES (?,?,?,?,?,?,?,?, current_timestamp)""",
            [tid, n, dacc, racc, mae, bt, status, flag])
    db.execute("CHECKPOINT")
    return {"templates_scored": len(by_t), "drift_alerts": drift,
            "promoted": promoted, "demoted": demoted}


# ── reporting helpers ──

def recommendation_accuracy(db: Database, window_days: int = 14) -> dict:
    rows = db.fetchall("""
        SELECT lp.recommendation, r.recommendation_correct, r.direction_correct, r.magnitude_error
        FROM prediction_resolutions r JOIN live_predictions lp ON lp.prediction_id = r.prediction_id
        WHERE r.window_days = ?""", [window_days])
    if not rows:
        return {"n": 0}
    by_rec: dict[str, list] = defaultdict(list)
    for rec, rok, dok, mae in rows:
        by_rec[rec].append((rok, dok, mae))
    n = len(rows)
    # EITHER is an ABSTENTION ("no strong preference"), not a committed call — it is
    # reported separately, not scored as a positive prediction. The product metric is
    # accuracy on the DECISIVE calls (ACT / WAIT / DO_NOT_ACT).
    decisive = [r for r in rows if r[0] != "EITHER"]
    nd = len(decisive)
    return {
        "n": n, "window_days": window_days,
        "decisive_n": nd,
        "decisive_recommendation_accuracy": (sum(1 for r in decisive if r[1]) / nd) if nd else 0.0,
        "blended_recommendation_accuracy": sum(1 for r in rows if r[1]) / n,
        "abstention_rate": (n - nd) / n,
        "direction_accuracy": sum(1 for r in rows if r[2]) / n,
        "magnitude_mae": sum(r[3] for r in rows) / n,
        "by_recommendation": {rec: {"n": len(v), "rec_acc": sum(x[0] for x in v) / len(v)}
                              for rec, v in by_rec.items()},
    }


# ── 5.5 Live state doc ──

def generate_live_state(db: Database, path: str) -> None:
    as_of = _data_max_date(db)
    n_acct = db.fetchone("SELECT count(DISTINCT account_id) FROM daily_metrics")[0]
    n_ep = db.fetchone("SELECT count(*) FROM episodes")[0]
    n_pred = db.fetchone("SELECT count(*) FROM live_predictions")[0]
    resolved = {w: db.fetchone("SELECT count(*) FROM prediction_resolutions WHERE window_days=?", [w])[0]
                for w in WINDOWS}
    pending = n_pred - resolved[7] if n_pred else 0
    rec14 = recommendation_accuracy(db, 14)
    health = dict(db.fetchall("SELECT status, count(*) FROM template_health GROUP BY 1"))
    drift = db.fetchall("SELECT template_id, live_direction_accuracy, backtest_direction_accuracy "
                        "FROM template_health WHERE drift_flag='DRIFT' ORDER BY 2 LIMIT 10")
    # noteworthy live calls this period
    strong = db.fetchall("""
        SELECT lp.recommendation, lp.template_id, lp.campaign_id, lp.action_cost_predicted,
               r.recommendation_correct
        FROM live_predictions lp JOIN prediction_resolutions r
          ON r.prediction_id=lp.prediction_id AND r.window_days=14
        WHERE lp.recommendation IN ('DO_NOT_ACT','ACT')
        ORDER BY abs(lp.action_cost_predicted) DESC LIMIT 8""")

    L = [f"# BrightMatter Live State — {as_of}", "",
         "*Auto-generated. Programmatic; no LLM in the loop.*", "",
         "## System health",
         f"- Accounts monitored: **{n_acct}** · data through **{as_of}**",
         f"- Episodes: **{n_ep}** · live predictions registered: **{n_pred}**",
         f"- Template health (live): " + " · ".join(f"{k} {v}" for k, v in health.items()) if health else
         "- Template health (live): (no resolutions yet)",
         f"- Resolved: 7d **{resolved[7]}** · 14d **{resolved[14]}** · 30d **{resolved[30]}** "
         f"(pending 7d resolution: {max(0,pending)})", ""]
    if rec14.get("n"):
        L += ["## Accuracy (14-day window — the product metric)",
              f"- Predictions resolved: **{rec14['n']}**",
              f"- **Recommendation accuracy (decisive calls): {rec14['decisive_recommendation_accuracy']*100:.0f}%** "
              f"(n={rec14['decisive_n']})",
              f"- Abstention rate (EITHER): {rec14['abstention_rate']*100:.0f}%",
              f"- Direction accuracy: {rec14['direction_accuracy']*100:.0f}% · "
              f"magnitude MAE: {rec14['magnitude_mae']*100:.0f}pp", "",
              "| Recommendation | n | correct |", "|---|---|---|"]
        for rec, s in sorted(rec14["by_recommendation"].items(), key=lambda kv: -kv[1]["n"]):
            L.append(f"| {rec} | {s['n']} | {s['rec_acc']*100:.0f}% |")
        L.append("")
    if drift:
        L += ["## Drift alerts", "| Template | live | backtest |", "|---|---|---|"]
        for tid, lv, bt in drift:
            L.append(f"| `{tid[:46]}` | {lv*100:.0f}% | {bt*100:.0f}% |")
        L.append("")
    if strong:
        L += ["## Noteworthy live calls (14d, strongest action-cost)", ""]
        for rec, tid, camp, cost, ok in strong:
            mark = "✓" if ok else "✗"
            L.append(f"- [{mark}] **{rec}** {tid[:44]} (campaign {camp}, "
                     f"predicted action cost {cost*100:+.0f}pp)")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
