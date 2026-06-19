"""Phase 2.4 — regime change detection (PELT).

A trend (2.1) is gradual drift; a regime change is a step to a NEW stable level
that persists. PELT (ruptures, L2 cost) finds the dates where a campaign's metric
shifted from one plateau to another — the most actionable temporal signal
("CPA was stable at $30 through Apr 15, then shifted to $42 and stayed there").

The series is standardized before PELT so one penalty is comparable across
metrics of different scale; min_size enforces that a "regime" lasts >= 2 weeks
(a spike that reverts in days is not a regime). Shifts are reported in original
units.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import ruptures as rpt

from brightmatter.storage.database import Database

MIN_SEGMENT_DAYS = 14
PENALTY = 3.0
MIN_POINTS = 2 * MIN_SEGMENT_DAYS  # need at least two full segments
METRICS = ("cpa", "cvr", "roas", "impression_share", "cost")


def detect_regime_changes(values: list[float], min_size: int = MIN_SEGMENT_DAYS,
                          penalty: float = PENALTY) -> list[int]:
    """Return changepoint indices (segment boundaries, excluding the final end)."""
    if len(values) < 2 * min_size:
        return []
    arr = np.array(values, dtype=float)
    std = arr.std()
    z = (arr - arr.mean()) / std if std > 0 else arr - arr.mean()
    algo = rpt.Pelt(model="l2", min_size=min_size).fit(z)
    bkps = algo.predict(pen=penalty)
    return [b for b in bkps if b < len(values)]


def _metric_value(row, metric: str):
    imp, clk, cost, conv, val, is_ = row[1:7]
    if metric == "cost":
        return cost
    if metric == "cvr":
        return conv / clk if clk else None
    if metric == "cpa":
        return cost / conv if conv else None
    if metric == "roas":
        return val / cost if cost else None
    if metric == "impression_share":
        return is_
    return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS regime_changes (
    account_id   TEXT NOT NULL,
    campaign_id  TEXT NOT NULL,
    metric       TEXT NOT NULL,
    change_date  DATE NOT NULL,
    pre_mean     DOUBLE,
    post_mean    DOUBLE,
    shift_magnitude DOUBLE,
    shift_direction TEXT,
    segment_days_before INTEGER,
    segment_days_after  INTEGER,
    computed_at  TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, metric, change_date)
);
"""


def run_regimes(db: Database, reset: bool = True, penalty: float = PENALTY) -> int:
    db.execute(SCHEMA)
    if reset:
        db.execute("DELETE FROM regime_changes")
    rows = db.fetchall("""
        SELECT account_id, campaign_id, date, impressions, clicks,
               cost_micros/1000000.0, conversions, conversion_value, search_impression_share
        FROM daily_metrics ORDER BY account_id, campaign_id, date
    """)
    series: dict[tuple[str, str], list] = {}
    for r in rows:
        series.setdefault((r[0], r[1]), []).append(
            (r[2], r[3] or 0, r[4] or 0, r[5] or 0.0, r[6] or 0, r[7] or 0.0, r[8]))

    now = datetime.now(timezone.utc)
    params = []
    for (acct, camp), days in series.items():
        for metric in METRICS:
            pts = [(row[0], _metric_value(row, metric)) for row in days]
            pts = [(d, v) for d, v in pts if v is not None]
            if len(pts) < MIN_POINTS:
                continue
            dts = [d for d, _ in pts]
            vals = [v for _, v in pts]
            bkps = detect_regime_changes(vals, penalty=penalty)
            prev = 0
            for bk in bkps:
                pre, post = vals[prev:bk], vals[bk:]
                if len(pre) < MIN_SEGMENT_DAYS or len(post) < MIN_SEGMENT_DAYS:
                    prev = bk
                    continue
                pre_mean, post_mean = float(np.mean(pre)), float(np.mean(post))
                shift = (post_mean - pre_mean) / pre_mean if pre_mean else 0.0
                params.append((acct, camp, metric, dts[bk], pre_mean, post_mean,
                               abs(shift), "up" if post_mean > pre_mean else "down",
                               len(pre), len(post), now))
                prev = bk
    if params:
        db.conn.executemany(
            "INSERT OR REPLACE INTO regime_changes VALUES (?,?,?,?,?,?,?,?,?,?,?)", params)
    try:
        db.execute("CHECKPOINT")
    except Exception:
        pass
    return len(params)
