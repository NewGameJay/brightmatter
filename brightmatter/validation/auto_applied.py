"""Disconfirmation harness for `detect_auto_applied_changes`.

Detector claim: auto-applied changes (Google's recommendations applied
automatically) can silently degrade performance. The signal counts auto-
applied changes in the last 30 days.

This is a *risk* signal, not a finding — the harness checks whether outcomes
actually moved, whether the volume is meaningful, and whether enough time
has passed to measure outcomes.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_outcome_correlation(db: Database, account_id: str) -> TestResult:
    """Did account-level metrics actually degrade after the auto-applied window?"""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT
          sum(CASE WHEN date >= current_date - 14 THEN cost_micros ELSE 0 END)/1000000.0 as recent_cost,
          sum(CASE WHEN date >= current_date - 14 THEN conversions ELSE 0 END) as recent_conv,
          sum(CASE WHEN date >= current_date - 28 AND date < current_date - 14 THEN cost_micros ELSE 0 END)/1000000.0 as base_cost,
          sum(CASE WHEN date >= current_date - 28 AND date < current_date - 14 THEN conversions ELSE 0 END) as base_conv
        FROM daily_metrics
        WHERE account_id = ?
        """, anchor),
        [account_id],
    )
    rcost, rconv, bcost, bconv = (row or (0, 0, 0, 0))
    rcost, rconv, bcost, bconv = (rcost or 0, rconv or 0, bcost or 0, bconv or 0)
    if not (rconv and bconv):
        return TestResult("T1", "Outcome movement after auto-changes", "inconclusive",
                          "Insufficient conversion data on one side of the comparison.")
    rcpa = rcost / rconv
    bcpa = bcost / bconv
    if not bcpa:
        return TestResult("T1", "Outcome movement after auto-changes", "inconclusive",
                          "Baseline CPA undefined.")
    delta = (rcpa - bcpa) / bcpa
    ev = [{"recent_cpa": round(rcpa, 2), "baseline_cpa": round(bcpa, 2),
           "cpa_change_pct": round(delta * 100, 1)}]
    if delta > 0.20:
        return TestResult("T1", "Outcome movement after auto-changes", "confirm",
                          f"Account CPA worsened {delta:+.0%} after the auto-applied window — outcome supports the concern.", ev)
    if delta < -0.10:
        return TestResult("T1", "Outcome movement after auto-changes", "disconfirm",
                          f"Account CPA improved {delta:+.0%} — auto-applied changes correlate with better outcomes here.", ev)
    return TestResult("T1", "Outcome movement after auto-changes", "inconclusive",
                      f"CPA roughly flat ({delta:+.0%}); auto-changes haven't visibly moved outcomes.", ev)


def test_volume_meaningful(account_id: str, data: dict) -> TestResult:
    """A handful of changes is probably noise; many implies real impact surface."""
    n = int(data.get("count") or 0)
    ev = [{"auto_applied_count": n}]
    if n >= 10:
        return TestResult("T2", "Auto-change volume meaningful", "confirm",
                          f"{n} auto-applied changes in 30d — large enough surface to plausibly affect outcomes.", ev)
    if n <= 2:
        return TestResult("T2", "Auto-change volume meaningful", "disconfirm",
                          f"Only {n} auto-applied change(s) — too few to plausibly drive account-level effects.", ev)
    return TestResult("T2", "Auto-change volume meaningful", "inconclusive",
                      f"{n} changes — moderate; impact likely campaign-specific.", ev)


def test_outcome_window_sufficient(db: Database, account_id: str, data: dict) -> TestResult:
    """If most changes happened in the last 7 days, there isn't enough post-data."""
    anchor = anchor_date(db)
    rows = db.fetchall(
        windowed("""
        SELECT change_timestamp
        FROM change_events
        WHERE account_id = ? AND actor = 'auto_applied'
          AND change_timestamp >= current_date - 30
        ORDER BY change_timestamp DESC
        """, anchor),
        [account_id],
    )
    if not rows:
        return TestResult("T3", "Outcome-data window sufficient", "inconclusive",
                          "No auto-applied changes found in change_events.")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    days = []
    for (ts,) in rows:
        try:
            if isinstance(ts, str):
                continue
            tz = ts.tzinfo or timezone.utc
            days.append((now.astimezone(tz) - ts).days)
        except Exception:
            continue
    if not days:
        return TestResult("T3", "Outcome-data window sufficient", "inconclusive",
                          "Could not parse change timestamps.")
    median_age = sorted(days)[len(days) // 2]
    ev = [{"median_change_age_days": median_age, "n_changes": len(days)}]
    if median_age < 7:
        return TestResult("T3", "Outcome-data window sufficient", "disconfirm",
                          f"Median change age {median_age}d — too recent to measure outcome impact.", ev)
    return TestResult("T3", "Outcome-data window sufficient", "confirm",
                      f"Median change age {median_age}d — enough post-change time to evaluate outcomes.", ev)


def audit_auto_applied_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'auto_applied_changes'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_outcome_correlation(db, acct_id),
            test_volume_meaningful(acct_id, data),
            test_outcome_window_sufficient(db, acct_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
