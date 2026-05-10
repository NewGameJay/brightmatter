"""Disconfirmation harness for `detect_cvr_anomalies` (cvr_drop).

Detector claim: a campaign whose CVR dropped >30% week-over-week has a real
performance issue (landing page degradation, tracking issue, etc.).

The harness tries to distinguish a real drop from artifacts: tracking changes,
campaign-type shifts, prior-week outliers, and pure volume noise.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


# ── Tests ──

def test_tracking_change_in_window(db: Database, account_id: str) -> TestResult:
    """T1 — A CONVERSION_ACTION change near the boundary explains the drop without performance loss.

    Vallaeys: 47% of stuck Smart Bidding campaigns trace to tracking issues. A
    CVR drop coincident with a conversion-tracking change is more likely a
    measurement artifact than a real degradation.
    """
    rows = db.fetchall(
        """
        SELECT change_timestamp, change_type, resource_type, actor
        FROM change_events
        WHERE account_id = ?
          AND change_timestamp >= current_date - 14
          AND (upper(resource_type) LIKE '%CONVERSION%' OR upper(change_type) LIKE '%CONVERSION%')
        ORDER BY change_timestamp DESC
        LIMIT 10
        """,
        [account_id],
    )
    ev = [{"timestamp": str(r[0]), "change_type": r[1],
           "resource_type": r[2], "actor": r[3]} for r in rows]
    if rows:
        return TestResult(
            "T1", "Tracking change in window", "disconfirm",
            f"{len(rows)} conversion-tracking change(s) within 14d of the drop — CVR change may be measurement, not performance.",
            ev,
        )
    return TestResult(
        "T1", "Tracking change in window", "confirm",
        "No conversion-tracking changes in the 14-day window — drop is not a tracking artifact.",
        ev,
    )


def test_campaign_type_stable(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """T2 — Did the campaign type or bidding strategy change mid-period?

    A switch from Search to PMax (or a bidding-strategy change) shifts the
    traffic mix, which can drop apparent CVR without any real degradation.
    """
    rows = db.fetchall(
        """
        SELECT DISTINCT campaign_type, bidding_strategy
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 14
        """,
        [account_id, campaign_id],
    )
    ev = [{"campaign_type": r[0], "bidding_strategy": r[1]} for r in rows]
    if len(rows) > 1:
        return TestResult(
            "T2", "Campaign-type / bidding-strategy stability", "disconfirm",
            f"Configuration changed during the comparison window: {len(rows)} distinct (type, strategy) combos — mix shift may explain CVR drop.",
            ev,
        )
    return TestResult(
        "T2", "Campaign-type / bidding-strategy stability", "confirm",
        "Campaign type and bidding strategy stable across the window.",
        ev,
    )


def test_volume_reliability(account_id: str, campaign_id: str, data: dict) -> TestResult:
    """T3 — If either week is low-volume, the CVR delta is statistical noise."""
    # The detector only fires when prior_clicks > 100 and prior_conv > 10, but
    # we can still flag cases where current week is on the edge.
    cur = data.get("current_cvr")
    prior = data.get("prior_cvr")
    ev = [{"current_cvr": cur, "prior_cvr": prior}]
    # We don't have raw counts in the signal data — read them.
    return TestResult(
        "T3", "Volume reliability vs threshold", "inconclusive",
        f"Detector pre-filtered for >100 clicks / >10 conv prior week (cvr {prior} → {cur}); raw weekly counts not stored on the signal.",
        ev,
    )


def test_prior_week_outlier(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """T4 — Was the prior week's CVR itself an outlier vs the surrounding history?

    If the prior 7d had unusually high CVR vs the broader 30d, the "drop" is
    just regression to the mean, not degradation.
    """
    rows = db.fetchall(
        """
        WITH weeks AS (
            SELECT
                CASE
                    WHEN date >= current_date - 7  THEN 'w1_current'
                    WHEN date >= current_date - 14 THEN 'w2_prior'
                    WHEN date >= current_date - 21 THEN 'w3_baseline_a'
                    WHEN date >= current_date - 28 THEN 'w4_baseline_b'
                    ELSE 'older'
                END as bucket,
                conversions, clicks
            FROM daily_metrics
            WHERE account_id = ? AND campaign_id = ?
              AND date >= current_date - 28
        )
        SELECT bucket, sum(conversions) as conv, sum(clicks) as clicks
        FROM weeks
        WHERE bucket != 'older'
        GROUP BY bucket
        """,
        [account_id, campaign_id],
    )
    by_bucket = {b: (c or 0, k or 0) for b, c, k in rows}
    cvrs = {b: ((c / k) if k else 0) for b, (c, k) in by_bucket.items()}
    ev = [{"weekly_cvrs": {k: round(v, 4) for k, v in cvrs.items()},
           "weekly_volume": {k: {"conv": v[0], "clicks": v[1]} for k, v in by_bucket.items()}}]
    prior = cvrs.get("w2_prior", 0)
    baseline = [cvrs.get("w3_baseline_a", 0), cvrs.get("w4_baseline_b", 0)]
    baseline = [b for b in baseline if b > 0]
    if not baseline:
        return TestResult(
            "T4", "Prior-week regression-to-mean check", "inconclusive",
            "Insufficient earlier history (w-3, w-4) to judge whether prior week was an outlier.",
            ev,
        )
    avg_baseline = sum(baseline) / len(baseline)
    if avg_baseline > 0 and prior > avg_baseline * 1.4:
        return TestResult(
            "T4", "Prior-week regression-to-mean check", "disconfirm",
            f"Prior-week CVR ({prior:.2%}) was {prior/avg_baseline:.1f}x the w3/w4 baseline ({avg_baseline:.2%}) — drop is largely regression to mean.",
            ev,
        )
    return TestResult(
        "T4", "Prior-week regression-to-mean check", "confirm",
        f"Prior-week CVR ({prior:.2%}) is consistent with w3/w4 baseline ({avg_baseline:.2%}); the drop is real, not mean reversion.",
        ev,
    )


# ── Orchestration ──

def audit_cvr_drop_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'cvr_drop'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_tracking_change_in_window(db, acct_id),
            test_campaign_type_stable(db, acct_id, camp_id),
            test_volume_reliability(acct_id, camp_id, data),
            test_prior_week_outlier(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
