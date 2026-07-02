"""Verification C3 — data integrity checksums.

Hash each day's ingested data per table. If the same date is re-ingested and the hash
differs (Google retroactive adjustments, a bad edit, corruption), we detect it before
it silently poisons templates (whitepaper 9.4).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from brightmatter.storage.database import Database

# table -> (date column expression)
_TABLES = {
    "daily_metrics": "date",
    "change_events": "CAST(change_timestamp AS DATE)",
    "search_terms": "window_end",
    "ga4_landing_pages": "date",
}


def _now():
    return datetime.now(timezone.utc)


def _content_hash(db: Database, table: str, date_expr: str, d) -> tuple[int, str]:
    rows = db.fetchall(f"SELECT * FROM {table} WHERE {date_expr} = ? ORDER BY 1,2", [d])
    payload = json.dumps([[str(x) for x in r] for r in rows], sort_keys=True)
    return len(rows), hashlib.sha256(payload.encode()).hexdigest()


def compute_checksums(db: Database, dates: list | None = None) -> dict:
    """Compute per-(date,table) checksums; flag any that differ from the prior run."""
    if dates is None:
        dates = [r[0] for r in db.fetchall("SELECT DISTINCT date FROM daily_metrics ORDER BY date")]
    changed = 0
    total = 0
    for d in dates:
        for table, expr in _TABLES.items():
            try:
                n, h = _content_hash(db, table, expr, d)
            except Exception:
                continue
            if n == 0:
                continue
            prev = db.fetchone("""SELECT content_hash FROM ingestion_checksums
                                  WHERE date=? AND table_name=? ORDER BY computed_at DESC LIMIT 1""", [d, table])
            prev_hash = prev[0] if prev else None
            hc = bool(prev_hash and prev_hash != h)
            if hc:
                changed += 1
            db.execute("""INSERT INTO ingestion_checksums
                (date, table_name, row_count, content_hash, previous_hash, hash_changed, computed_at)
                VALUES (?,?,?,?,?,?,?)""", [d, table, n, h, prev_hash, hc, _now()])
            total += 1
    db.execute("CHECKPOINT")
    return {"checksums": total, "mismatches": changed}


def verify_checksums(db: Database) -> dict:
    """Any date whose most recent hash differs from its prior hash = a mismatch."""
    m = db.fetchone("SELECT count(*) FROM ingestion_checksums WHERE hash_changed") [0]
    dates = db.fetchone("SELECT count(DISTINCT date) FROM ingestion_checksums")[0]
    return {"ok": m == 0, "dates_verified": dates, "mismatches": m}
