"""Phase 4.75 — Matched controls + the Act-vs-Wait decision framework.

4.75.1 build_matched_controls()  -> same-campaign, same-state, no-action counterfactuals
4.75.3 should_act() / categorize_templates() -> ACT / WAIT / DO_NOT_ACT / EITHER

The central question this answers, for any campaign + proposed action: is acting
better than doing nothing, and by how much? It compares the template's prediction
(what happens if you act) to the natural trajectory (what happens if you don't),
upgrading the population counterfactual from 4.5.1 to a within-campaign matched
control where one exists.

CPA convention (from Phase 4): signed change, NEGATIVE = improvement. action_cost
= template_prediction − natural_trajectory; POSITIVE = acting leaves CPA higher
(worse) than waiting.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import timedelta

from brightmatter.storage.database import Database
from brightmatter.patterns import templates as T
from brightmatter.patterns import refine

PRE = refine.PRE
POST = refine.POST
MATCH_WINDOW_DAYS = 60
ACT_THRESHOLD = 0.10       # |action_cost| below this = "either"
STRONG_AVOID = 0.20        # action_cost above this = "do not act"


# ── 4.75.1 Matched controls ──

def build_matched_controls(db: Database, episodes: list[dict] | None = None) -> dict:
    """Match each episode to a no-action window on the SAME campaign in the SAME
    state, non-overlapping and within 60 days. The campaign is its own control,
    removing the cross-campaign selection bias of the 4.5.1 population baseline."""
    eps = episodes if episodes is not None else refine.refine_episodes(db)

    # baseline windows grouped by (campaign, state)
    base: dict[tuple, list] = defaultdict(list)
    for camp, state, ws, we, chg in db.fetchall("""
        SELECT campaign_id, state, window_start, window_end, cpa_change_pct
        FROM baseline_observations
    """):
        base[(camp, state)].append((ws, we, chg))

    db.execute("DELETE FROM matched_controls")
    matched = []
    for e in eps:
        cd = e.get("change_date")
        if cd is None or not e["campaign_id"]:
            continue
        ew_start, ew_end = cd - timedelta(days=PRE), cd + timedelta(days=POST)
        cands = base.get((e["campaign_id"], e["pre_state"]), [])
        best = None
        for ws, we, chg in cands:
            if we <= ew_start or ws >= ew_end:                       # non-overlapping
                gap = min(abs((ws - cd).days), abs((we - cd).days))
                if gap <= MATCH_WINDOW_DAYS and (best is None or gap < best[0]):
                    best = (gap, ws, chg)
        if best is None:
            continue
        attribution = e["signed"] - best[2]
        rec = {"episode_id": e["episode_id"], "campaign_id": e["campaign_id"],
               "state": e["pre_state"], "action_cpa_change": e["signed"],
               "no_action_cpa_change": best[2], "matched_attribution": attribution,
               "gap_days": best[0]}
        matched.append(rec)
        db.execute("""INSERT INTO matched_controls
            (episode_id, campaign_id, state, action_cpa_change, no_action_cpa_change,
             matched_attribution, match_quality, baseline_window_start)
            VALUES (?,?,?,?,?,?,?,?)""",
            [rec["episode_id"], rec["campaign_id"], rec["state"], e["signed"],
             best[2], attribution, "same_campaign_same_state", best[1]])
    db.execute("CHECKPOINT")

    # per-state matched vs population comparison
    by_state: dict[str, list] = defaultdict(list)
    for m in matched:
        by_state[m["state"]].append(m["matched_attribution"])
    summary = {st: {"matched_median": statistics.median(v), "n": len(v)}
               for st, v in by_state.items()}
    return {"matched": matched, "match_rate": len(matched) / max(1, len(eps)),
            "n_episodes": len(eps), "n_matched": len(matched), "by_state": summary}


# ── natural trajectory (no-action baseline) ──

def natural_trajectory(db: Database) -> dict[str, float]:
    """Median no-action CPA change per state, from baseline_observations."""
    return {st: med for st, med in db.fetchall(
        "SELECT state, median(cpa_change_pct) FROM baseline_observations GROUP BY 1")}


# ── 4.75.3 Act-vs-wait decision ──

def _decision(action_cost: float) -> tuple[str, str]:
    if action_cost is None:
        return "WAIT", "No template/natural baseline to compare — default to waiting."
    if action_cost >= STRONG_AVOID:
        return "DO_NOT_ACT", (f"Acting leaves CPA ~{action_cost*100:.0f}pp higher than "
                              f"doing nothing — a real, large action penalty.")
    if action_cost >= ACT_THRESHOLD:
        return "WAIT", (f"Acting costs ~{action_cost*100:.0f}pp of CPA vs. the natural "
                        f"trajectory; the campaign likely moves on its own.")
    if action_cost <= -ACT_THRESHOLD:
        return "ACT", (f"Acting improves CPA ~{abs(action_cost)*100:.0f}pp beyond the "
                       f"natural trajectory — a genuine action benefit.")
    return "EITHER", (f"Acting and waiting are within {abs(action_cost)*100:.0f}pp — "
                      f"no strong preference.")


def should_act(db: Database, account_id: str, campaign_id: str, action_category: str,
               is_multi: bool = False, natural: dict | None = None) -> dict:
    """For a campaign + proposed action: ACT / WAIT / DO_NOT_ACT / EITHER, with the
    do-nothing forecast always stated."""
    natural = natural if natural is not None else natural_trajectory(db)
    row = db.fetchone("""
        SELECT COALESCE(NULLIF(business_type,''),'unknown'),
               COALESCE(NULLIF(vertical,''),'unknown'),
               COALESCE(NULLIF(spend_tier,''),'unknown')
        FROM accounts WHERE account_id=?""", [account_id])
    if not row:
        return {"error": f"unknown account {account_id}"}
    biz, vert, tier = row
    st = db.fetchone("""SELECT pre_state FROM episodes WHERE account_id=? AND campaign_id=?
                        AND pre_state IS NOT NULL AND pre_state<>'' ORDER BY recorded_at DESC LIMIT 1""",
                     [account_id, campaign_id])
    state = st[0] if st else "stable"
    nat = natural.get(state)

    base = {"change_category": action_category, "is_multi_action": is_multi,
            "business_type": biz, "vertical": vert, "spend_tier": tier, "pre_state": state}
    tmpl = None
    for keys in T._LEVELS:
        cond = {k: base[k] for k in keys}
        r = db.fetchone("""SELECT prediction_direction, prediction_magnitude,
                                  action_attributable_magnitude, n_episodes, direction_accuracy, status
                           FROM templates WHERE template_id=? AND status IN ('ACTIVE','PROVISIONAL')
                           ORDER BY version DESC LIMIT 1""", [T.template_id_of(cond)])
        if r:
            tmpl = r
            break
    if tmpl is None or nat is None:
        return {"account_id": account_id, "campaign_id": campaign_id, "state": state,
                "action": action_category, "decision": "WAIT",
                "reason": "No matching active template for this profile — insufficient evidence to recommend acting."}

    pred_dir, pred_mag, attributable, n, acc, status = tmpl
    # matched-control attribution for this campaign+state if it exists, else template's
    mc = db.fetchone("""SELECT median(matched_attribution), count(*) FROM matched_controls
                        WHERE campaign_id=? AND state=?""", [campaign_id, state])
    action_cost = (attributable if attributable is not None else (pred_mag - nat))
    matched_note = None
    if mc and mc[1] and mc[0] is not None:
        action_cost = mc[0]
        matched_note = f"same-campaign matched control (n={mc[1]}): {mc[0]*100:+.0f}pp"
    decision, reason = _decision(action_cost)
    return {
        "account_id": account_id, "campaign_id": campaign_id, "state": state,
        "business_type": biz, "vertical": vert, "spend_tier": tier,
        "action": action_category, "multi_action": is_multi,
        "do_nothing_forecast_pct": round(nat * 100, 1),
        "template_prediction_pct": round(pred_mag * 100, 1),
        "action_cost_pp": round(action_cost * 100, 1),
        "matched_control": matched_note,
        "template_basis": f"{n} episodes, {acc*100:.0f}% dir, {status}",
        "decision": decision, "reason": reason,
    }


def categorize_templates(db: Database) -> dict:
    """Re-categorize the catalog by action-attributable effect (computed in 4.5.1):
    do-nothing (action ~= natural), dont-do-this (action much worse), act-now
    (action much better)."""
    rows = db.fetchall("""
        SELECT template_id, prediction_direction, prediction_magnitude,
               natural_magnitude, action_attributable_magnitude, n_episodes, direction_accuracy
        FROM templates WHERE status IN ('ACTIVE','PROVISIONAL')
              AND action_attributable_magnitude IS NOT NULL""")
    cats = {"act_now": [], "dont_do_this": [], "do_nothing": []}
    for tid, d, pm, nm, attr, n, acc in rows:
        rec = {"template_id": tid, "prediction": d, "pred_mag": pm, "natural": nm,
               "attributable": attr, "n": n, "dir_acc": acc}
        if attr <= -ACT_THRESHOLD:
            cats["act_now"].append(rec)
        elif attr >= ACT_THRESHOLD:
            cats["dont_do_this"].append(rec)
        else:
            cats["do_nothing"].append(rec)
    for k in cats:
        cats[k].sort(key=lambda r: -abs(r["attributable"]))
    return cats
