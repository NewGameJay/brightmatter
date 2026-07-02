"""Verification C8 — drift & anomaly logging. Structured, queryable audit trail."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from brightmatter.storage.database import Database


def _now():
    return datetime.now(timezone.utc)


def log_event(db: Database, event_type: str, severity: str, details: dict,
              related_entity: str | None = None) -> str:
    eid = hashlib.sha256(f"{event_type}|{related_entity}|{_now().isoformat()}".encode()).hexdigest()[:16]
    db.execute("""INSERT OR REPLACE INTO verification_events
        (event_id, event_type, severity, details, related_entity, created_at)
        VALUES (?,?,?,?,?,?)""",
        [eid, event_type, severity, json.dumps(details, default=str), related_entity, _now()])
    return eid


def sync_drift_events(db: Database) -> int:
    """Mirror current template_health DRIFT flags into the event log (idempotent per
    template while unresolved)."""
    n = 0
    try:
        drift = db.fetchall("""SELECT template_id, live_direction_accuracy, backtest_direction_accuracy
                               FROM template_health WHERE drift_flag='DRIFT'""")
    except Exception:
        return 0
    for tid, live, bt in drift:
        exists = db.fetchone("""SELECT 1 FROM verification_events WHERE event_type='drift_alert'
                                AND related_entity=? AND resolved_at IS NULL""", [tid])
        if exists:
            continue
        log_event(db, "drift_alert", "warning",
                  {"template_id": tid, "live_acc": live, "backtest_acc": bt,
                   "delta_pp": round(((live or 0) - (bt or 0)) * 100, 1)}, tid)
        n += 1
    db.execute("CHECKPOINT")
    return n


def count_unresolved(db: Database, event_type: str | None = None) -> int:
    if event_type:
        return db.fetchone("SELECT count(*) FROM verification_events WHERE resolved_at IS NULL AND event_type=?",
                           [event_type])[0]
    return db.fetchone("SELECT count(*) FROM verification_events WHERE resolved_at IS NULL")[0]


def count_recent(db: Database, days: int = 7) -> int:
    return db.fetchone(f"""SELECT count(*) FROM verification_events
                           WHERE created_at >= (SELECT max(created_at) FROM verification_events) - INTERVAL {int(days)} DAY""")[0] or 0
