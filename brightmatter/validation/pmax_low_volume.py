"""Disconfirmation harness for `detect_pmax_low_conversion_volume`.

Detector claim: PMax campaign has <30 conv/month — Smart Bidding can't
optimize. Same caveats as insufficient_conversions_for_strategy but
PMax-specific: status, recency, value-based signal, age.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def test_campaign_active(db: Database, account_id: str, campaign_id: str) -> TestResult:
    rows = db.fetchall(
        """
        SELECT status, count(*) as days
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
        GROUP BY status
        """,
        [account_id, campaign_id],
    )
    by_status = {r[0]: r[1] for r in rows}
    enabled = by_status.get("ENABLED", 0)
    other = sum(v for k, v in by_status.items() if k != "ENABLED")
    ev = [{"status_breakdown": by_status}]
    if enabled == 0 or other > enabled:
        return TestResult("T1", "Campaign active across window", "disconfirm",
                          f"Campaign was inactive most/all of the window ({by_status}) — low convs reflect activity, not optimization.",
                          ev)
    return TestResult("T1", "Campaign active across window", "confirm",
                      f"Campaign primarily ENABLED ({enabled}d).", ev)


def test_value_per_conversion(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """High value per conversion partially offsets low count for tROAS optimization."""
    row = db.fetchone(
        """
        SELECT sum(conversion_value) as v, sum(conversions) as c
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
        """,
        [account_id, campaign_id],
    )
    val, conv = (row or (0, 0))
    val, conv = (val or 0, conv or 0)
    if not conv:
        return TestResult("T2", "Value-per-conversion sufficiency", "inconclusive",
                          "Zero conversions — claim stands by definition.",
                          [{"value_30d": val, "conversions_30d": 0}])
    vpc = val / conv
    ev = [{"value_30d": round(val, 2), "conv_30d": conv, "value_per_conv": round(vpc, 2)}]
    if vpc >= 500 and conv >= 10:
        return TestResult("T2", "Value-per-conversion sufficiency", "disconfirm",
                          f"${vpc:.0f} per conversion across {conv:.0f} conversions — high-AOV PMax can optimize on value despite count.",
                          ev)
    return TestResult("T2", "Value-per-conversion sufficiency", "confirm",
                      f"${vpc:.0f}/conv at {conv:.0f} convs — neither count nor value compensates.",
                      ev)


def test_share_of_account_spend(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """A small-spend PMax campaign is a test, not a structural problem."""
    row = db.fetchone(
        """
        WITH camp_spend AS (
          SELECT campaign_id, sum(cost_micros)/1000000.0 as cost
          FROM daily_metrics
          WHERE account_id = ? AND date >= current_date - 30
          GROUP BY campaign_id
        )
        SELECT
          (SELECT cost FROM camp_spend WHERE campaign_id = ?) as this_cost,
          (SELECT sum(cost) FROM camp_spend) as total_cost
        """,
        [account_id, campaign_id],
    )
    this_cost, total_cost = (row or (0, 0))
    this_cost, total_cost = (this_cost or 0, total_cost or 0)
    if not total_cost:
        return TestResult("T3", "Share of account spend", "inconclusive",
                          "No spend in account.")
    share = this_cost / total_cost
    ev = [{"this_cost": round(this_cost, 2), "total_cost": round(total_cost, 2),
           "share": round(share, 3)}]
    if share < 0.05:
        return TestResult("T3", "Share of account spend", "disconfirm",
                          f"PMax is only {share:.0%} of account spend — small test, not an optimization concern.",
                          ev)
    return TestResult("T3", "Share of account spend", "confirm",
                      f"PMax holds {share:.0%} of account spend — meaningful share; low convs matter.",
                      ev)


def test_campaign_age(db: Database, account_id: str, campaign_id: str) -> TestResult:
    row = db.fetchone(
        """
        SELECT min(date), max(date) FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
        """,
        [account_id, campaign_id],
    )
    first, last = (row or (None, None))
    if not first or not last:
        return TestResult("T4", "Campaign age", "inconclusive", "No date range.")
    age = (last - first).days + 1
    ev = [{"first_seen": str(first), "last_seen": str(last), "age_days": age}]
    if age < 21:
        return TestResult("T4", "Campaign age", "disconfirm",
                          f"PMax visible only {age}d — Google's own guidance says 6+ weeks before judging volume.",
                          ev)
    return TestResult("T4", "Campaign age", "confirm",
                      f"PMax visible for {age}d — past initial ramp; volume claim is real.",
                      ev)


def audit_pmax_low_volume_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'pmax_low_conv_volume'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_campaign_active(db, acct_id, camp_id),
            test_value_per_conversion(db, acct_id, camp_id),
            test_share_of_account_spend(db, acct_id, camp_id),
            test_campaign_age(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
