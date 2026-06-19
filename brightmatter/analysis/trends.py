"""Phase 2.1 — rolling trend detection.

OLS (scipy.stats.linregress) over 7/14/30-day windows for each campaign metric.
A slope + p-value + r² is explainable ("CPA rising $2.30/week, p=0.03") and fast.
Trends are the temporal context the rest of Phase 2 layers on: signal annotation
(2.2), episode trend-adjustment (2.3), volatility (2.5).

projected_7d = current + slope×7 is "if the current trend continues unchanged" —
NOT a prediction (that's Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np
from scipy.stats import linregress

from brightmatter.storage.database import Database

WINDOWS = (7, 14, 30)
MIN_POINTS = 7
VOLATILE_CV = 0.30
SIG_P = 0.10

# +1 = higher is better, -1 = lower is better, 0 = no inherent good direction.
FAVORABLE = {"cpa": -1, "cvr": 1, "ctr": 1, "roas": 1, "impression_share": 1, "cost": 0}


@dataclass
class TrendResult:
    slope: float
    p_value: float
    r_squared: float
    classification: str
    cv: float
    current_value: float
    projected_7d: float


def compute_trend(dates: list[date], values: list[float], metric: str,
                  min_points: int = MIN_POINTS) -> TrendResult | None:
    """OLS trend over a (dates, values) series for one metric."""
    if len(values) < min_points:
        return None
    x = np.array([(d - dates[0]).days for d in dates], dtype=float)
    y = np.array(values, dtype=float)
    if np.ptp(x) == 0:
        return None
    res = linregress(x, y)
    slope, p = float(res.slope), float(res.pvalue)
    mean = float(np.mean(y))
    cv = float(np.std(y) / abs(mean)) if mean else 0.0
    current = float(y[-1])
    projected = current + slope * 7

    fav = FAVORABLE.get(metric, 0)
    if cv > VOLATILE_CV:
        cls = "volatile"
    elif np.isnan(p) or p >= SIG_P:
        cls = "stable"
    elif fav == 0:
        cls = "rising" if slope > 0 else "falling"
    else:
        cls = "improving" if (slope * fav > 0) else "declining"
    return TrendResult(slope, p, float(res.rvalue) ** 2, cls, cv, current, projected)


def _daily_value(row: dict, metric: str) -> float | None:
    """Per-day metric value, or None when undefined (e.g. CPA on a 0-conv day)."""
    imp, clk = row["impressions"], row["clicks"]
    cost, conv, val = row["cost"], row["conversions"], row["conversion_value"]
    if metric == "cost":
        return cost
    if metric == "ctr":
        return clk / imp if imp else None
    if metric == "cvr":
        return conv / clk if clk else None
    if metric == "cpa":
        return cost / conv if conv else None
    if metric == "roas":
        return val / cost if cost else None
    if metric == "impression_share":
        return row["impression_share"]
    return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_trends (
    account_id     TEXT NOT NULL,
    campaign_id    TEXT NOT NULL,
    metric         TEXT NOT NULL,
    window_days    INTEGER NOT NULL,
    slope          DOUBLE,
    p_value        DOUBLE,
    r_squared      DOUBLE,
    classification TEXT,
    cv             DOUBLE,
    current_value  DOUBLE,
    projected_7d   DOUBLE,
    volatility_cv       DOUBLE,
    volatility_class    TEXT DEFAULT '',
    threshold_multiplier DOUBLE DEFAULT 1.0,
    computed_at    TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (account_id, campaign_id, metric, window_days)
);
"""


def run_trends(db: Database, reset: bool = True) -> int:
    """Compute trends for every campaign with >= MIN_POINTS days, all metrics/windows."""
    db.execute(SCHEMA)
    if reset:
        db.execute("DELETE FROM campaign_trends")
    anchor = db.fetchone("SELECT max(date) FROM daily_metrics")
    if not anchor or anchor[0] is None:
        return 0
    anchor = anchor[0]

    rows = db.fetchall("""
        SELECT account_id, campaign_id, date, impressions, clicks,
               cost_micros / 1000000.0, conversions, conversion_value,
               search_impression_share
        FROM daily_metrics
        ORDER BY account_id, campaign_id, date
    """)
    series: dict[tuple[str, str], list[dict]] = {}
    for acct, camp, d, imp, clk, cost, conv, val, is_ in rows:
        series.setdefault((acct, camp), []).append(
            {"date": d, "impressions": imp or 0, "clicks": clk or 0, "cost": cost or 0.0,
             "conversions": conv or 0, "conversion_value": val or 0.0, "impression_share": is_})

    now = datetime.now(timezone.utc)
    params = []
    for (acct, camp), days in series.items():
        if len({r["date"] for r in days}) < MIN_POINTS:
            continue
        for window in WINDOWS:
            start = anchor - timedelta(days=window - 1)
            wdays = [r for r in days if start <= r["date"] <= anchor]
            for metric in FAVORABLE:
                pts = [(r["date"], _daily_value(r, metric)) for r in wdays]
                pts = [(d, v) for d, v in pts if v is not None]
                if len(pts) < MIN_POINTS:
                    continue
                t = compute_trend([d for d, _ in pts], [v for _, v in pts], metric)
                if t is None:
                    continue
                params.append((acct, camp, metric, window, t.slope, t.p_value,
                               t.r_squared, t.classification, t.cv, t.current_value,
                               t.projected_7d, None, "", 1.0, now))
    if params:
        db.conn.executemany("""
            INSERT OR REPLACE INTO campaign_trends VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, params)
    try:
        db.execute("CHECKPOINT")
    except Exception:
        pass
    return len(params)
