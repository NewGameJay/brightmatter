"""Disconfirmation harness for `detect_duplicate_primary_conversions`.

Detector claim: 3+ ENABLED primary conversion actions = double-counting.

Disconfirmation hinges on whether the multiple primary actions represent
genuinely distinct conversion goals (lead + purchase + appointment) or
true duplication of the same goal (3 PURCHASE actions counted separately).
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_distinct_categories(db: Database, account_id: str) -> TestResult:
    """If categories are distinct, multi-goal tracking is intentional, not dup."""
    try:
        rows = db.fetchall(
            """
            SELECT category, count(*) as n
            FROM conversion_actions
            WHERE account_id = ? AND primary_for_goal = true AND status = 'ENABLED'
            GROUP BY category
            """,
            [account_id],
        )
    except Exception as e:
        return TestResult("T1", "Distinct conversion categories", "inconclusive",
                          f"conversion_actions query failed: {e}")
    if not rows:
        return TestResult("T1", "Distinct conversion categories", "inconclusive",
                          "No conversion actions found — claim cannot be evaluated.")
    by_cat = {r[0]: r[1] for r in rows}
    ev = [{"categories": by_cat}]
    n_categories = len(by_cat)
    same_category_dup = max(by_cat.values()) >= 2
    if n_categories >= 3 and not same_category_dup:
        return TestResult("T1", "Distinct conversion categories", "disconfirm",
                          f"All primary actions are in distinct categories ({list(by_cat)}); multi-goal tracking, not duplication.",
                          ev)
    if same_category_dup:
        worst = max(by_cat, key=lambda k: by_cat[k])
        return TestResult("T1", "Distinct conversion categories", "confirm",
                          f"Category '{worst}' has {by_cat[worst]} primary actions — same-goal duplication.",
                          ev)
    return TestResult("T1", "Distinct conversion categories", "inconclusive",
                      f"Mixed: {by_cat} — some overlap, some distinct goals.", ev)


def test_inflated_count_vs_clicks(db: Database, account_id: str) -> TestResult:
    """If conversions/clicks exceeds plausible (>40% across the account), suspect double-counting."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) as conv, sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id],
    )
    conv, clicks = (row or (0, 0))
    conv = conv or 0
    clicks = clicks or 0
    if not clicks:
        return TestResult("T2", "CVR plausibility check", "inconclusive",
                          "No clicks in window.")
    cvr = conv / clicks
    ev = [{"account_cvr_30d": round(cvr, 4), "conversions": conv, "clicks": clicks}]
    if cvr > 0.50:
        return TestResult("T2", "CVR plausibility check", "confirm",
                          f"Account CVR is {cvr:.0%} — implausibly high; multi-counting is likely.",
                          ev)
    if cvr < 0.20:
        return TestResult("T2", "CVR plausibility check", "disconfirm",
                          f"Account CVR is {cvr:.0%} — within plausible range; multi-action setup isn't visibly inflating numbers.",
                          ev)
    return TestResult("T2", "CVR plausibility check", "inconclusive",
                      f"Account CVR is {cvr:.0%} — borderline.", ev)


def test_value_per_conversion(db: Database, account_id: str) -> TestResult:
    """Same-goal duplication often produces unrealistically low value-per-conversion."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) as conv, sum(conversion_value) as value
        FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id],
    )
    conv, val = (row or (0, 0))
    conv = conv or 0
    val = val or 0
    ev = [{"value_per_conversion": round(val / conv, 2) if conv else None}]
    if not conv:
        return TestResult("T3", "Value-per-conversion plausibility", "inconclusive",
                          "No conversions to evaluate.", ev)
    if val == 0:
        return TestResult("T3", "Value-per-conversion plausibility", "inconclusive",
                          "Conversion value is $0 — no value tracking; can't judge.", ev)
    vpc = val / conv
    if vpc < 1:
        return TestResult("T3", "Value-per-conversion plausibility", "confirm",
                          f"Value per conversion is ${vpc:.2f} — implausibly low; many 'conversions' are likely duplicates with no real value.",
                          ev)
    return TestResult("T3", "Value-per-conversion plausibility", "inconclusive",
                      f"Value per conversion ${vpc:.2f} — neither implausibly low nor diagnostic.", ev)


def audit_duplicate_primary_conversions_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'duplicate_primary_conversions'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_distinct_categories(db, acct_id),
            test_inflated_count_vs_clicks(db, acct_id),
            test_value_per_conversion(db, acct_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
