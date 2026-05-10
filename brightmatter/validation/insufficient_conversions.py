"""Disconfirmation harness for `detect_bidding_antipatterns` (insufficient_conversions_for_strategy).

Detector claim: campaign uses tCPA/tROAS with <15 conv/month — Smart Bidding
can't optimize without enough conversion data.

Disconfirmation tests look for: campaigns that are paused/zombie, recent
strategy changes that haven't accumulated data yet, conversion-value (not
count) sufficiency for tROAS, and brand-new campaigns still ramping.
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
    ev = [{"status_breakdown": by_status}]
    enabled = by_status.get("ENABLED", 0)
    other = sum(v for k, v in by_status.items() if k != "ENABLED")
    if enabled == 0:
        return TestResult("T1", "Campaign currently active", "disconfirm",
                          f"Campaign was never ENABLED in window ({by_status}); claim of insufficient data is moot.",
                          ev)
    if other > enabled:
        return TestResult("T1", "Campaign currently active", "disconfirm",
                          f"Campaign was inactive most of window (enabled={enabled}d, other={other}d); low convs explained by inactivity.",
                          ev)
    return TestResult("T1", "Campaign currently active", "confirm",
                      f"Campaign primarily ENABLED ({enabled}d); low conv volume reflects real optimization gap.",
                      ev)


def test_strategy_recency(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """If the bidding strategy was changed mid-window, low convs are expected."""
    rows = db.fetchall(
        """
        SELECT DISTINCT bidding_strategy, min(date) as first_seen, max(date) as last_seen
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
          AND bidding_strategy IS NOT NULL
        GROUP BY bidding_strategy
        ORDER BY first_seen
        """,
        [account_id, campaign_id],
    )
    ev = [{"strategy_periods": [(s, str(f), str(l)) for s, f, l in rows]}]
    if len(rows) > 1:
        return TestResult("T2", "Strategy recency", "disconfirm",
                          f"Bidding strategy changed within the 30d window ({len(rows)} distinct values) — low convs expected during transition, not a misconfiguration.",
                          ev)
    return TestResult("T2", "Strategy recency", "confirm",
                      "Bidding strategy stable across the window — low conv volume isn't from a recent switch.",
                      ev)


def test_conversion_value_sufficiency(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """For tROAS, total revenue may be enough even with few transactions."""
    strategy = (data.get("strategy") or "").upper()
    if strategy != "TARGET_ROAS":
        return TestResult("T3", "Conversion-value sufficiency (tROAS)", "inconclusive",
                          f"Strategy is {strategy or 'unknown'}, not TARGET_ROAS — value-based test doesn't apply.")
    row = db.fetchone(
        """
        SELECT sum(conversion_value) as value, sum(conversions) as conv
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
        """,
        [account_id, campaign_id],
    )
    val, conv = (row or (0, 0))
    val, conv = (val or 0, conv or 0)
    ev = [{"value_30d": round(val, 2), "conversions_30d": conv}]
    if val >= 5000 and conv >= 8:
        return TestResult("T3", "Conversion-value sufficiency (tROAS)", "disconfirm",
                          f"${val:,.0f} of value across {conv:.0f} conversions — tROAS can use value signal even at this volume.",
                          ev)
    if val < 500:
        return TestResult("T3", "Conversion-value sufficiency (tROAS)", "confirm",
                          f"Only ${val:,.0f} of conversion value — insufficient signal for tROAS.",
                          ev)
    return TestResult("T3", "Conversion-value sufficiency (tROAS)", "inconclusive",
                      f"${val:,.0f} value across {conv:.0f} conversions — borderline.",
                      ev)


def test_campaign_age(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """Brand-new campaigns haven't had time to accumulate convs."""
    row = db.fetchone(
        """
        SELECT min(date) as first_date, max(date) as last_date
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
        """,
        [account_id, campaign_id],
    )
    first, last = (row or (None, None))
    if not first or not last:
        return TestResult("T4", "Campaign age", "inconclusive",
                          "No date range available.")
    age_days = (last - first).days + 1
    ev = [{"first_seen": str(first), "last_seen": str(last), "age_days": age_days}]
    if age_days < 14:
        return TestResult("T4", "Campaign age", "disconfirm",
                          f"Campaign visible in data for only {age_days}d — too young to have accumulated 15+ conv/month.",
                          ev)
    return TestResult("T4", "Campaign age", "confirm",
                      f"Campaign visible for {age_days}d — old enough that low convs are a real signal, not new-campaign ramp.",
                      ev)


def audit_insufficient_conversions_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'insufficient_conversions_for_strategy'
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
            test_strategy_recency(db, acct_id, camp_id),
            test_conversion_value_sufficiency(db, acct_id, camp_id, data),
            test_campaign_age(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
