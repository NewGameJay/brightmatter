"""Disconfirmation harness for `detect_vertical_cpa_benchmark`.

Detector claim: this account's CPA is >3x the published market benchmark for
its vertical — expensive for the industry.

The benchmark is a coarse market average, so the alternatives are the same as
for cross_account_outlier plus benchmark-fit:
  T1 — high CPA is justified by high conversion value (good ROAS), not waste
  T2 — the gap is egregious (well beyond benchmark noise) vs merely above
  T3 — the account is too new to judge (learning phase)
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_value_justifies_cpa(db: Database, account_id: str, data: dict) -> TestResult:
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversion_value) as val, sum(cost_micros) / 1000000.0 as cost
        FROM daily_metrics WHERE account_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id],
    )
    val, cost = (row or (0, 0))
    val, cost = (val or 0, cost or 0)
    if val <= 0:
        return TestResult("T1", "Value justifies CPA", "inconclusive",
                          "No conversion value tracked — can't tell if the high CPA buys high-value conversions.",
                          [{"conversion_value_30d": val}])
    roas = val / cost if cost else 0
    ev = [{"roas": round(roas, 2)}]
    if roas >= 3:
        return TestResult("T1", "Value justifies CPA", "disconfirm",
                          f"ROAS {roas:.1f}x — the high CPA buys high-value conversions; above-benchmark CPA isn't inefficiency.",
                          ev)
    if roas < 1:
        return TestResult("T1", "Value justifies CPA", "confirm",
                          f"ROAS {roas:.1f}x — the above-benchmark CPA isn't offset by value; genuinely expensive.",
                          ev)
    return TestResult("T1", "Value justifies CPA", "inconclusive",
                      f"ROAS {roas:.1f}x — borderline.", ev)


def test_gap_magnitude(data: dict) -> TestResult:
    ratio = data.get("ratio") or 0
    ev = [{"ratio_to_benchmark": round(ratio, 1), "vertical": data.get("vertical"),
           "expected_cpa": data.get("expected_cpa")}]
    if ratio >= 5:
        return TestResult("T2", "Gap magnitude vs benchmark", "confirm",
                          f"CPA is {ratio:.1f}x the vertical benchmark — far beyond benchmark noise.", ev)
    return TestResult("T2", "Gap magnitude vs benchmark", "inconclusive",
                      f"CPA is {ratio:.1f}x benchmark — above the line but within the range coarse benchmarks can mislead on.",
                      ev)


def test_account_maturity(db: Database, account_id: str) -> TestResult:
    row = db.fetchone(
        "SELECT min(date), max(date) FROM daily_metrics WHERE account_id = ?",
        [account_id],
    )
    first, last = (row or (None, None))
    if not first or not last:
        return TestResult("T3", "Account maturity", "inconclusive", "No date range.")
    age = (last - first).days + 1
    ev = [{"age_days": age}]
    if age < 30:
        return TestResult("T3", "Account maturity", "disconfirm",
                          f"Only {age}d of data — may be ramping; CPA isn't yet steady-state.", ev)
    return TestResult("T3", "Account maturity", "confirm",
                      f"{age}d of data — established; the CPA gap reflects steady state.", ev)


def audit_vertical_cpa_benchmark_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'vertical_cpa_benchmark'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_value_justifies_cpa(db, acct_id, data),
            test_gap_magnitude(data),
            test_account_maturity(db, acct_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
