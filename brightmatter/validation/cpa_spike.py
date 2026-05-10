"""Disconfirmation harness for `detect_cpa_spikes`.

Detector claim: campaign's recent (7d) CPA exceeds 3x its 30-day baseline —
something has degraded.

Tests look for the common artifacts: recent low volume, single-day spikes,
bidding-strategy changes, and conversion-value lifts that justify the cost.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def test_recent_volume(db: Database, account_id: str, campaign_id: str) -> TestResult:
    row = db.fetchone(
        """
        SELECT sum(conversions) as conv, sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 7
        """,
        [account_id, campaign_id],
    )
    conv, clicks = (row or (0, 0))
    conv = conv or 0
    ev = [{"conversions_7d": conv, "clicks_7d": clicks}]
    if conv < 5:
        return TestResult(
            "T1", "Recent-week volume reliability", "disconfirm",
            f"Only {conv:.1f} conversions in 7d — recent CPA is dominated by noise, not a real spike.",
            ev,
        )
    if conv >= 15:
        return TestResult(
            "T1", "Recent-week volume reliability", "confirm",
            f"{conv:.0f} recent conversions — CPA estimate is reliable.",
            ev,
        )
    return TestResult(
        "T1", "Recent-week volume reliability", "inconclusive",
        f"{conv:.0f} recent conversions — borderline.", ev,
    )


def test_single_day_outlier(db: Database, account_id: str, campaign_id: str) -> TestResult:
    rows = db.fetchall(
        """
        SELECT date, cost_micros / 1000000.0 as cost, conversions
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 7
        ORDER BY date
        """,
        [account_id, campaign_id],
    )
    if not rows:
        return TestResult("T2", "Single-day outlier", "inconclusive", "No daily data.", [])
    costs = [r[1] or 0 for r in rows]
    total = sum(costs) or 1
    max_share = max(costs) / total
    ev = [{"daily_cost_share_max": round(max_share, 3),
           "daily_cost": [round(c, 2) for c in costs]}]
    if max_share > 0.50:
        return TestResult(
            "T2", "Single-day outlier", "disconfirm",
            f"One day accounts for {max_share:.0%} of the recent week's spend — CPA spike is a single-day artifact.",
            ev,
        )
    return TestResult(
        "T2", "Single-day outlier", "confirm",
        f"Spend distributed across the week (max-day share {max_share:.0%}); spike isn't from one bad day.",
        ev,
    )


def test_bidding_strategy_stability(db: Database, account_id: str, campaign_id: str) -> TestResult:
    rows = db.fetchall(
        """
        SELECT DISTINCT bidding_strategy
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
          AND bidding_strategy IS NOT NULL
        """,
        [account_id, campaign_id],
    )
    ev = [{"strategies_seen": [r[0] for r in rows]}]
    if len(rows) > 1:
        return TestResult(
            "T3", "Bidding-strategy stability", "disconfirm",
            f"Strategy changed during baseline ({len(rows)} distinct values) — CPA spike likely reflects strategy switch, not degradation.",
            ev,
        )
    return TestResult(
        "T3", "Bidding-strategy stability", "confirm",
        "Bidding strategy stable across baseline + recent window.",
        ev,
    )


def test_conversion_value_movement(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    row = db.fetchone(
        """
        SELECT
          sum(CASE WHEN date >= current_date - 7 THEN conversion_value ELSE 0 END) as recent_v,
          sum(CASE WHEN date >= current_date - 7 THEN conversions ELSE 0 END) as recent_c,
          sum(CASE WHEN date >= current_date - 30 AND date < current_date - 7 THEN conversion_value ELSE 0 END) as base_v,
          sum(CASE WHEN date >= current_date - 30 AND date < current_date - 7 THEN conversions ELSE 0 END) as base_c
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
        """,
        [account_id, campaign_id],
    )
    rv, rc, bv, bc = (row or (0, 0, 0, 0))
    rv, rc, bv, bc = (rv or 0, rc or 0, bv or 0, bc or 0)
    if not rc or not bc:
        return TestResult(
            "T4", "Conversion-value lift offsets CPA", "inconclusive",
            "Insufficient conversion data on one side.",
        )
    recent_aov = rv / rc if rc else 0
    base_aov = bv / bc if bc else 0
    if not base_aov:
        return TestResult("T4", "Conversion-value lift offsets CPA", "inconclusive",
                          "Baseline AOV is zero (no value tracking?).")
    aov_lift = recent_aov / base_aov
    ev = [{"recent_aov": round(recent_aov, 2), "base_aov": round(base_aov, 2),
           "aov_lift": round(aov_lift, 2)}]
    if aov_lift >= 2.0:
        return TestResult(
            "T4", "Conversion-value lift offsets CPA", "disconfirm",
            f"AOV rose {aov_lift:.1f}x in recent window — higher CPA is buying higher-value conversions, not degraded performance.",
            ev,
        )
    return TestResult(
        "T4", "Conversion-value lift offsets CPA", "confirm",
        f"AOV roughly stable ({aov_lift:.1f}x) — CPA spike isn't justified by higher-value conversions.",
        ev,
    )


def audit_cpa_spike_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'cpa_spike'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_recent_volume(db, acct_id, camp_id),
            test_single_day_outlier(db, acct_id, camp_id),
            test_bidding_strategy_stability(db, acct_id, camp_id),
            test_conversion_value_movement(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
