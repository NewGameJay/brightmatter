"""Verification C2 + C7 + C5 — provenance chain, spot-check, accuracy export.

C2: which episodes formed which template version (template_episode_links) + a frozen
    provenance snapshot per prediction (survives later re-extraction).
C7: spot_check — the real episodes (accounts, changes, before/after metrics) behind a
    recommendation, so trust is earned case by case.
C5: export_accuracy_audit — a flat CSV anyone can recompute accuracy from.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from brightmatter.storage.database import Database
from brightmatter.patterns import refine, magnitude as M


def _now():
    return datetime.now(timezone.utc)


def build_template_episode_links(db: Database) -> int:
    """Record which episodes fall into each magnitude-aware template (the set that
    formed it). Frozen so a later re-extraction doesn't erase the original evidence."""
    eps = M.attach_magnitude(db, refine.refine_episodes(db))
    assigned = M.assign_mag_templates(eps)
    db.execute("DELETE FROM template_episode_links")
    n = 0
    for tid, members in assigned.items():
        for m in members:
            db.execute("""INSERT OR REPLACE INTO template_episode_links
                (template_id, template_version, episode_id) VALUES (?, 1, ?)""",
                ["mag:" + tid if not tid.startswith("mag:") else tid, m["episode_id"]])
            n += 1
    db.execute("CHECKPOINT")
    return n


def store_provenance(db: Database, prediction_id: str, template_id: str,
                     episode_ids: list[str], baseline_n: int, template_hash: str | None) -> str:
    payload = json.dumps({"prediction_id": prediction_id, "template_id": template_id,
                          "episode_ids": sorted(episode_ids), "baseline_n": baseline_n,
                          "template_hash": template_hash}, sort_keys=True)
    phash = hashlib.sha256(payload.encode()).hexdigest()
    db.execute("""INSERT OR REPLACE INTO prediction_provenance
        (prediction_id, template_id, template_version, template_hash, episode_count,
         episode_ids, baseline_n, provenance_hash, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        [prediction_id, template_id, 1, template_hash, len(episode_ids),
         json.dumps(sorted(episode_ids)), baseline_n, phash, _now()])
    return phash


def spot_check(db: Database, account_id: str, campaign_id: str, action_category: str | None = None,
               n_examples: int = 5) -> dict:
    """Real episodes behind a recommendation for this campaign, ranked by state match."""
    st = db.fetchone("""SELECT pre_state FROM episodes WHERE account_id=? AND campaign_id=?
                        AND pre_state<>'' ORDER BY recorded_at DESC LIMIT 1""", [account_id, campaign_id])
    if not st:
        return {"error": "no state for campaign"}
    state = st[0]
    cat = action_category
    if cat is None:
        c = db.fetchone("""SELECT change_category FROM episodes WHERE account_id=? AND campaign_id=?
                           ORDER BY recorded_at DESC LIMIT 1""", [account_id, campaign_id])
        cat = c[0] if c else None
    rows = db.fetchall("""
        SELECT e.episode_id, COALESCE(a.account_name,''), e.campaign_id, e.pre_state,
               e.change_category, e.actor, e.outcome, e.outcome_magnitude,
               e.pre_metrics_json, e.post_metrics_json, e.recorded_at
        FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id
        WHERE e.change_category=? AND e.pre_state=? AND e.outcome<>'confounded'
        ORDER BY (e.account_id=?) DESC, e.recorded_at DESC LIMIT ?""",
        [cat, state, account_id, n_examples])
    examples = []
    for r in rows:
        pre = json.loads(r[8]) if r[8] else {}
        post = json.loads(r[9]) if r[9] else {}
        examples.append({
            "account": r[1], "campaign": r[2], "state_before": r[3], "change": r[4],
            "actor": r[5], "outcome": r[6], "magnitude": round(r[7] or 0, 3),
            "cpa_before": pre.get("cpa"), "cpa_after": post.get("cpa"),
            "cvr_before": pre.get("cvr"), "cvr_after": post.get("cvr"),
            "date": str(r[10])[:10],
        })
    return {"state": state, "action": cat, "n_examples": len(examples), "examples": examples}


def export_accuracy_audit(db: Database, output_path: str) -> int:
    """Flat CSV: one row per resolved per-metric prediction. No derived columns — the
    auditor computes accuracy/MAE themselves and checks it against the system's numbers."""
    rows = db.fetchall("""
        SELECT mp.prediction_id, mp.episode_id, mp.template_id, mp.metric,
               mp.predicted_median, mp.predicted_iqr_low, mp.predicted_iqr_high,
               mp.actual_delta, mp.error, mp.within_iqr,
               lp.recommendation, lp.state, lp.predicted_direction,
               mp.registered_at, mp.resolved_at
        FROM metric_predictions mp
        LEFT JOIN live_predictions lp ON lp.episode_id = mp.episode_id
        WHERE mp.resolved ORDER BY mp.registered_at""")
    headers = ["prediction_id", "episode_id", "template_id", "metric", "predicted_median",
               "iqr_low", "iqr_high", "actual_delta", "abs_error", "within_iqr",
               "recommendation", "state", "predicted_direction", "registered_at", "resolved_at"]
    with open(output_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(headers)
        for r in rows:
            w.writerow([str(x) if x is not None else "" for x in r])
    return len(rows)
