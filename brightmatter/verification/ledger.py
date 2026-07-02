"""Verification C1 — append-only prediction ledger with chain hashing.

Every prediction is written once, hashed, and chained to the previous. Modifying any
row breaks the chain for every subsequent row — an auditor recomputes the whole chain
in one pass. This is a Merkle chain without the blockchain (whitepaper 11.3).

The working table (live_predictions / metric_predictions) stays; the ledger is a
parallel append-only record proving the prediction existed when it claims.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from brightmatter.storage.database import Database


def _now():
    return datetime.now(timezone.utc)


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, default=str)


def register_to_ledger(db: Database, prediction: dict) -> str:
    """Append one prediction. Ledger write is authoritative — call BEFORE the working
    table write. Returns the chain_hash. Idempotent on prediction_id (skips dupes)."""
    pid = prediction["prediction_id"]
    if db.fetchone("SELECT 1 FROM prediction_ledger WHERE prediction_id=?", [pid]):
        return db.fetchone("SELECT chain_hash FROM prediction_ledger WHERE prediction_id=?", [pid])[0]
    payload = _canonical(prediction)
    pred_hash = hashlib.sha256(payload.encode()).hexdigest()
    prev = db.fetchone("SELECT chain_hash FROM prediction_ledger ORDER BY seq DESC LIMIT 1")
    chain_hash = hashlib.sha256(((prev[0] if prev else "genesis") + pred_hash).encode()).hexdigest()
    db.execute("""INSERT INTO prediction_ledger
        (seq, prediction_id, payload, prediction_hash, chain_hash, created_at)
        VALUES (nextval('ledger_seq'), ?, ?, ?, ?, ?)""",
        [pid, payload, pred_hash, chain_hash, prediction.get("timestamp") or _now()])
    return chain_hash


def resolve_in_ledger(db: Database, prediction_id: str, actual_direction: str,
                      actual_metrics: dict) -> None:
    """Write the outcome ONCE. Refuses to overwrite an existing resolution."""
    row = db.fetchone("SELECT resolved_at FROM prediction_ledger WHERE prediction_id=?", [prediction_id])
    if not row or row[0] is not None:
        return
    payload = _canonical({"actual_direction": actual_direction, "actual_metrics": actual_metrics})
    rhash = hashlib.sha256(payload.encode()).hexdigest()
    db.execute("""UPDATE prediction_ledger SET resolved_at=?, actual_direction=?,
                  actual_metrics=?, resolution_hash=? WHERE prediction_id=?""",
               [_now(), actual_direction, _canonical(actual_metrics), rhash, prediction_id])


def verify_ledger_integrity(db: Database) -> dict:
    """Recompute every hash and confirm the chain. Returns {ok, n, break_at}."""
    rows = db.fetchall("""SELECT seq, prediction_id, payload, prediction_hash, chain_hash
                          FROM prediction_ledger ORDER BY seq""")
    prev = "genesis"
    for seq, pid, payload, phash, chash in rows:
        exp_p = hashlib.sha256(payload.encode()).hexdigest()
        if exp_p != phash:
            return {"ok": False, "n": len(rows), "break_at": seq, "reason": "payload tampered"}
        exp_c = hashlib.sha256((prev + exp_p).encode()).hexdigest()
        if exp_c != chash:
            return {"ok": False, "n": len(rows), "break_at": seq, "reason": "chain broken"}
        prev = chash
    return {"ok": True, "n": len(rows), "break_at": None}
