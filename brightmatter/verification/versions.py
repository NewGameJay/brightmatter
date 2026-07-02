"""Verification C4 + C6 — template version hashing + reproducibility test.

Each template version's full state (conditions, per-metric predictions, the episode
IDs that formed it, accuracy) is serialized, hashed, and linked to the git commit of
the extraction code. Reproducibility: re-derive the hashes from current episodes and
compare — deterministic system => identical hashes (whitepaper 4.3, 4.3.2).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from brightmatter.storage.database import Database


def _now():
    return datetime.now(timezone.utc)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _version_hash(tid, version, conditions, predictions, episode_ids, n_ep, n_acc, acc) -> str:
    payload = json.dumps({
        "template_id": tid, "version": version, "conditions": conditions,
        "predictions": predictions, "episode_ids": sorted(episode_ids),
        "n_episodes": n_ep, "n_accounts": n_acc, "direction_accuracy": acc,
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def snapshot_template_versions(db: Database, commit: str | None = None) -> int:
    """Freeze + hash every current template into template_versions, with its per-metric
    predictions and the episode IDs that formed it (from template_episode_links)."""
    commit = commit or git_commit()
    templates = db.fetchall("""SELECT template_id, version, conditions_json, prediction_direction,
                                      n_episodes, n_accounts, direction_accuracy, created_at
                               FROM templates""")
    n = 0
    for tid, ver, cond, pdir, n_ep, n_acc, acc, created in templates:
        preds = db.fetchall("""SELECT metric, median_delta, iqr_low, iqr_high FROM per_metric_predictions
                               WHERE template_id=? OR template_id=?""", [tid, "mag:" + tid])
        predictions = {m: [md, lo, hi] for m, md, lo, hi in preds}
        eids = [r[0] for r in db.fetchall(
            "SELECT episode_id FROM template_episode_links WHERE template_id=? AND template_version=?", [tid, ver])]
        vh = _version_hash(tid, ver, cond, predictions, eids, n_ep, n_acc, acc)
        db.execute("""INSERT OR REPLACE INTO template_versions
            (template_id, version, conditions_json, predictions_json, episode_ids_json,
             n_episodes, n_accounts, direction_accuracy, version_hash, code_commit, extracted_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [tid, ver, cond, json.dumps(predictions), json.dumps(sorted(eids)),
             n_ep, n_acc, acc, vh, commit, created or _now()])
        n += 1
    db.execute("CHECKPOINT")
    return n


def reproducibility_test(db: Database) -> dict:
    """Re-derive each template's version_hash from CURRENT data (conditions + per-metric
    predictions + episode links) and compare to the frozen template_versions hash.
    Deterministic => all match. Divergence => new data (expected) or manual edit."""
    prod = db.fetchall("""SELECT template_id, version, version_hash FROM template_versions
                          WHERE retired_at IS NULL""")
    mism = []
    checked = 0
    for tid, ver, stored in prod:
        t = db.fetchone("""SELECT conditions_json, n_episodes, n_accounts, direction_accuracy
                           FROM templates WHERE template_id=? AND version=?""", [tid, ver])
        if not t:
            mism.append(f"{tid} v{ver}: in versions but not in templates"); continue
        cond, n_ep, n_acc, acc = t
        preds = db.fetchall("""SELECT metric, median_delta, iqr_low, iqr_high FROM per_metric_predictions
                               WHERE template_id=? OR template_id=?""", [tid, "mag:" + tid])
        predictions = {m: [md, lo, hi] for m, md, lo, hi in preds}
        eids = [r[0] for r in db.fetchall(
            "SELECT episode_id FROM template_episode_links WHERE template_id=? AND template_version=?", [tid, ver])]
        fresh = _version_hash(tid, ver, cond, predictions, eids, n_ep, n_acc, acc)
        checked += 1
        if fresh != stored:
            mism.append(f"{tid} v{ver}: hash differs (stored {stored[:12]} vs fresh {fresh[:12]})")
    return {"ok": not mism, "checked": checked, "mismatches": mism}
