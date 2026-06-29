"""Per-episode pipeline trace — the 6-stage observability view, from real tables.

build_pipeline_trace(db, account_id, campaign_id) assembles the same shape the
BrightMatter Pipeline UI renders (analysis → changes → patterns → recommendation →
decision → monitoring) for the campaign's most recent episode, entirely from stored
data. Honest gaps are emitted as nulls with a status, never fabricated:
  - Stage 4 narrative is a STRUCTURED reason (no LLM prose).
  - Stage 5 marketer follow/override/ignore is null until the human-in-loop layer
    (forward deployment) exists; we DO have the change actor (auto vs human).
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.patterns import actwait, templates as T


def _latest_episode(db, account_id, campaign_id):
    return db.fetchone("""
        SELECT e.episode_id, e.change_event_id, e.pre_state, e.change_category, e.change_count,
               e.actor, e.outcome, e.pre_metrics_json, e.post_metrics_json
        FROM episodes e WHERE e.account_id=? AND e.campaign_id=?
        ORDER BY e.recorded_at DESC LIMIT 1""", [account_id, campaign_id])


def build_pipeline_trace(db: Database, account_id: str, campaign_id: str) -> dict:
    ep = _latest_episode(db, account_id, campaign_id)
    acct = db.fetchone("""SELECT COALESCE(account_name,''), COALESCE(NULLIF(business_type,''),'unknown'),
                          COALESCE(NULLIF(vertical,''),'unknown'), COALESCE(NULLIF(spend_tier,''),'unknown')
                          FROM accounts WHERE account_id=?""", [account_id]) or ("", "unknown", "unknown", "unknown")
    name, biz, vert, tier = acct
    trace = {"account": name, "account_id": account_id, "campaign_id": campaign_id,
             "vertical": vert, "tier": tier, "business_type": biz}
    if not ep:
        trace["error"] = "no episode for this campaign"
        return trace
    (eid, ceid, state, category, count, eactor, outcome, pre_json, post_json) = ep
    pre = json.loads(pre_json) if pre_json else {}
    post = json.loads(post_json) if post_json else {}

    # ── 1. ANALYSIS ──
    sigs = db.fetchall("""SELECT signal_type, severity, message, COALESCE(confidence_tier,'')
                          FROM signals WHERE account_id=? AND (campaign_id=? OR campaign_id='')
                          ORDER BY detected_at DESC LIMIT 8""", [account_id, campaign_id])
    ga4 = db.fetchone("""SELECT avg(engagement_rate),
                           avg(CASE WHEN device='mobile' THEN engagement_rate END),
                           avg(CASE WHEN device='desktop' THEN engagement_rate END),
                           avg(bounce_rate)
                         FROM ga4_landing_pages WHERE account_id=?""", [account_id])
    trace["analysis"] = {
        "state": state,
        "signals": [{"type": s[0], "severity": s[1], "message": s[2], "confidence": s[3] or None} for s in sigs],
        "metrics": {"cpa": pre.get("cpa"), "roas": pre.get("roas"), "cvr": pre.get("cvr")},
        "ga4": ({"engagement": round(ga4[0], 3), "mobile_engagement": round(ga4[1], 3) if ga4[1] else None,
                 "desktop_engagement": round(ga4[2], 3) if ga4[2] else None, "bounce": round(ga4[3], 3)}
                if ga4 and ga4[0] is not None else None),
    }

    # ── 2. CHANGES ──
    events = db.fetchall("""SELECT resource_type, change_type, old_value, new_value, actor, change_timestamp
                            FROM change_events WHERE account_id=? AND change_id=?""", [account_id, ceid])
    trace["changes"] = {
        "events": [{"type": e[0], "change_type": e[1], "actor": e[4], "date": str(e[5])[:10]} for e in events],
        "category": category, "bundle": category if (count or 1) > 1 else None,
        "confounded": outcome == "confounded", "episode_id": eid, "actor": eactor,
        "change_count": count,
    }

    # ── 3. PATTERNS ──
    # the episode's magnitude-aware template per-metric prediction
    from brightmatter.patterns import magnitude as M, refine
    eps = refine.refine_episodes(db)
    erow = next((e for e in eps if e["episode_id"] == eid), None)
    per_metric, tmpl_id = {}, None
    if erow:
        M.attach_magnitude(db, [erow])
        for keys in M._MAG_LEVELS:
            tid = "mag:" + M._mag_id({k: erow[k] for k in keys})
            rows = db.fetchall("""SELECT metric, median_delta, iqr_low, iqr_high, mae, n
                                  FROM per_metric_predictions WHERE template_id=? ORDER BY mae""", [tid])
            if rows:
                tmpl_id = tid
                per_metric = {m: {"median": round(md, 3), "range": [round(lo, 3), round(hi, 3)],
                                  "mae_pp": round(mae * 100, 1), "n": n} for m, md, lo, hi, mae, n in rows}
                break
    natural = actwait.natural_trajectory(db).get(state)
    mc = db.fetchone("SELECT median(matched_attribution), count(*) FROM matched_controls WHERE campaign_id=? AND state=?",
                     [campaign_id, state])
    trace["patterns"] = {
        "template_id": tmpl_id, "per_metric_prediction": per_metric,
        "do_nothing_forecast_pct": round(natural * 100, 1) if natural is not None else None,
        "matched_control": ({"attribution_pp": round(mc[0] * 100, 1), "n": mc[1]} if mc and mc[1] else None),
    }

    # ── 4. RECOMMENDATION ──
    rec = actwait.should_act(db, account_id, campaign_id, category, is_multi=(count or 1) > 1)
    trace["recommendation"] = {
        "call": rec.get("decision"), "reason": rec.get("reason"),
        "do_nothing_forecast_pct": rec.get("do_nothing_forecast_pct"),
        "action_cost_pp": rec.get("action_cost_pp"), "matched_control": rec.get("matched_control"),
        "basis": rec.get("template_basis"),
    }

    # ── 5. DECISION ──
    trace["decision"] = {
        "change_actor": eactor,
        "status": "auto_applied" if eactor == "auto_applied" else "human" if eactor == "human" else "unknown",
        "marketer_response": None,
        "note": ("Google auto-applied this change; no human approval sought."
                 if eactor == "auto_applied" else
                 "Human-made change (actor=human). Whether a marketer saw/followed a BrightMatter "
                 "recommendation is not tracked — that requires the forward-deployment human-in-loop layer."),
    }

    # ── 6. MONITORING ──
    res = db.fetchall("""SELECT metric, predicted_median, actual_delta, error, within_iqr
                         FROM metric_predictions WHERE episode_id=? AND resolved ORDER BY error""", [eid])
    scoring = {}
    for m, pmed, actual, err, within in res:
        bucket = ("exact" if err <= 0.05 else "close" if err <= 0.10 else "ballpark" if err <= 0.20 else "miss")
        scoring[m] = {"predicted": round(pmed, 3), "actual": round(actual, 3),
                      "error_pp": round(err * 100, 1), "score": bucket, "within_iqr": bool(within)}
    trace["monitoring"] = {
        "resolved": bool(res), "metric_scoring": scoring,
        "episode_outcome": outcome,
    }
    return trace
