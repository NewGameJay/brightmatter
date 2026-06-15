"""Disconfirmation harness for `detect_cross_account_outlier`.

Detector claim: this account's CPA is >2σ above its segment peers — it pays
far more per conversion than similar accounts.

The confidence framework lists the alternatives Google Ads data can't rule
out: different conversion types, markets, price points, and account maturity.
These tests probe exactly those:
  T1 — high CPA is justified by high conversion value (high-ticket, good ROAS)
  T2 — the comparison fell back to a mixed-vertical group (apples-to-oranges)
  T3 — the account is too new to judge (learning phase)
  T4 — too few conversions for the CPA to be stable
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_value_justifies_cpa(db: Database, account_id: str, data: dict) -> TestResult:
    """A high CPA with high conversion value (good ROAS) isn't inefficiency."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversion_value) as val, sum(cost_micros) / 1000000.0 as cost,
               sum(conversions) as conv
        FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id],
    )
    val, cost, conv = (row or (0, 0, 0))
    val, cost, conv = (val or 0, cost or 0, conv or 0)
    if val <= 0:
        return TestResult("T1", "Value justifies CPA", "inconclusive",
                          "No conversion value tracked — can't tell if the high CPA buys high-value conversions.",
                          [{"conversion_value_30d": val}])
    roas = val / cost if cost else 0
    vpc = val / conv if conv else 0
    ev = [{"roas": round(roas, 2), "value_per_conv": round(vpc, 2), "cpa": data.get("cpa")}]
    if roas >= 3:
        return TestResult("T1", "Value justifies CPA", "disconfirm",
                          f"ROAS {roas:.1f}x (value/conv ${vpc:,.0f}) — the high CPA buys high-value conversions; not inefficiency.",
                          ev)
    if roas < 1:
        return TestResult("T1", "Value justifies CPA", "confirm",
                          f"ROAS {roas:.1f}x — the high CPA isn't offset by conversion value; genuinely inefficient.",
                          ev)
    return TestResult("T1", "Value justifies CPA", "inconclusive",
                      f"ROAS {roas:.1f}x — borderline; CPA is high but not clearly unprofitable.", ev)


def test_comparison_basis(db: Database, data: dict) -> TestResult:
    """An outlier vs vertical peers is apples-to-apples; vs a global/mixed group
    it could just reflect different conversion types or markets."""
    seg = data.get("segment", "global")
    ev = [{"segment": seg, "segment_label": data.get("segment_label"), "peer_n": data.get("peer_n")}]
    if seg in ("vertical+tier", "vertical"):
        return TestResult("T2", "Peer comparison basis", "confirm",
                          f"Compared within its own vertical segment ({data.get('segment_label')}, n={data.get('peer_n')}) — apples-to-apples.",
                          ev)
    if seg == "spend_tier":
        return TestResult("T2", "Peer comparison basis", "inconclusive",
                          f"Compared only within spend tier ({data.get('segment_label')}) — same scale, but mixed verticals/conversion types.",
                          ev)
    return TestResult("T2", "Peer comparison basis", "disconfirm",
                      "Compared against ALL accounts (no vertical/tier peer group) — the gap may reflect different conversion types or markets, not inefficiency.",
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
    ev = [{"first_seen": str(first), "last_seen": str(last), "age_days": age}]
    if age < 30:
        return TestResult("T3", "Account maturity", "disconfirm",
                          f"Only {age}d of data — may be in learning/ramp; CPA isn't yet a steady-state comparison.",
                          ev)
    return TestResult("T3", "Account maturity", "confirm",
                      f"{age}d of data — established enough that the CPA gap reflects steady state.", ev)


def test_volume_sufficiency(db: Database, account_id: str, data: dict) -> TestResult:
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id],
    )
    conv = (row[0] if row and row[0] else 0)
    ev = [{"conversions_30d": conv}]
    if conv >= 100:
        return TestResult("T4", "Conversion volume sufficiency", "confirm",
                          f"{conv:.0f} conv in 30d — the CPA estimate is stable.", ev)
    return TestResult("T4", "Conversion volume sufficiency", "inconclusive",
                      f"{conv:.0f} conv in 30d — adequate but not abundant; CPA has some noise.", ev)


def audit_cross_account_outlier_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'cross_account_cpa_outlier'
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
            test_comparison_basis(db, data),
            test_account_maturity(db, acct_id),
            test_volume_sufficiency(db, acct_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
