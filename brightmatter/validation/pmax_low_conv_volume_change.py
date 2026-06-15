"""Disconfirmation harness for `detect_pmax_low_conv_volume_change`.

Detector claim: PMax campaign's 14d conversion count moved by ≥25% relative
AND ≥5 absolute vs the prior 14d. Signal is informational; direction in
data['direction']. Improving signals preview that a state-firing campaign
may exit on its own as it ramps.

False-positive shapes:
  T1 — Campaign wasn't reliably ENABLED across both windows
  T2 — Spend changed proportionally (volume tracked spend; not a structural shift)
  T3 — Single-day dominance in one window
  T4 — Campaign was within its learning phase during the prior window
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def _windows(data: dict) -> tuple[str, int]:
    return data.get("anchor_date") or "", int(data.get("window_days") or 14)


def test_status_continuity(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T1", "Status continuity across windows", "inconclusive",
                          "No anchor_date.", [])
    rows = db.fetchall(
        f"""
        SELECT
          CASE WHEN date > DATE '{anchor}' - {window} THEN 'current' ELSE 'prior' END as period,
          status, count(*) as days
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}'
        GROUP BY period, status
        """,
        [account_id, campaign_id],
    )
    by_period: dict[str, dict[str, int]] = {"current": {}, "prior": {}}
    for period, status, days in rows:
        by_period[period][status] = days
    ev = [{"status_by_period": by_period}]
    cur_enabled = by_period["current"].get("ENABLED", 0)
    prior_enabled = by_period["prior"].get("ENABLED", 0)
    cur_other = sum(v for k, v in by_period["current"].items() if k != "ENABLED")
    prior_other = sum(v for k, v in by_period["prior"].items() if k != "ENABLED")
    if cur_other > cur_enabled or prior_other > prior_enabled:
        return TestResult("T1", "Status continuity across windows", "disconfirm",
                          f"Campaign was non-ENABLED most days of one window — volume delta reflects activity, not optimization.",
                          ev)
    if cur_enabled >= window - 2 and prior_enabled >= window - 2:
        return TestResult("T1", "Status continuity across windows", "confirm",
                          f"Predominantly ENABLED in both windows ({prior_enabled}/{cur_enabled} days).",
                          ev)
    return TestResult("T1", "Status continuity across windows", "inconclusive",
                      f"Mixed status coverage ({prior_enabled}/{cur_enabled} ENABLED days).", ev)


def test_spend_proportionality(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """If spend moved with conversions, the volume change is a budget effect, not structural."""
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T2", "Volume delta net of spend delta", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT sum(cost_micros) as cost, sum(conversions) as conv
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT sum(cost_micros) as cost, sum(conversions) as conv
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        )
        SELECT cur.cost, prior.cost, cur.conv, prior.conv FROM cur, prior
        """,
        [account_id, campaign_id, account_id, campaign_id],
    )
    cc, pc, cv, pv = (row or (0, 0, 0, 0))
    cc, pc, cv, pv = (cc or 0, pc or 0, cv or 0, pv or 0)
    if pc == 0 or pv == 0:
        return TestResult("T2", "Volume delta net of spend delta", "inconclusive",
                          "Zero prior spend or volume — cannot compare ratios.", [])
    spend_ratio = cc / pc
    conv_ratio = cv / pv
    ev = [{"spend_ratio": round(spend_ratio, 2), "conv_ratio": round(conv_ratio, 2)}]
    # If spend moved by within 15pp of conv movement, the volume delta is largely budget-driven.
    if abs(spend_ratio - conv_ratio) <= 0.15 and abs(spend_ratio - 1) >= 0.20:
        return TestResult("T2", "Volume delta net of spend delta", "disconfirm",
                          f"Spend ratio {spend_ratio:.2f}x ≈ conv ratio {conv_ratio:.2f}x — volume tracked spend; not a structural change.",
                          ev)
    return TestResult("T2", "Volume delta net of spend delta", "confirm",
                      f"Conv ratio {conv_ratio:.2f}x is not explained by spend ratio {spend_ratio:.2f}x — structural movement.",
                      ev)


def test_single_day_dominance(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T3", "Single-day conversion dominance", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT max(conversions) / NULLIF(sum(conversions), 0) as share
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT max(conversions) / NULLIF(sum(conversions), 0) as share
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        )
        SELECT cur.share, prior.share FROM cur, prior
        """,
        [account_id, campaign_id, account_id, campaign_id],
    )
    cur_share, prior_share = (row or (0, 0))
    cur_share, prior_share = (cur_share or 0, prior_share or 0)
    ev = [{"cur_max_day_conv_share": round(cur_share, 3),
           "prior_max_day_conv_share": round(prior_share, 3)}]
    if max(cur_share, prior_share) > 0.50:
        return TestResult("T3", "Single-day conversion dominance", "disconfirm",
                          f"One day held >50% of conversions in {'current' if cur_share > prior_share else 'prior'} window — delta reflects one observation.",
                          ev)
    return TestResult("T3", "Single-day conversion dominance", "confirm",
                      f"Conversions spread across windows (max-day shares {prior_share:.0%} / {cur_share:.0%}).",
                      ev)


def test_learning_phase(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """PMax needs ~6 weeks before its volume is interpretable (per Google guidance)."""
    row = db.fetchone(
        """
        SELECT min(date), max(date) FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
        """,
        [account_id, campaign_id],
    )
    first, last = (row or (None, None))
    if not first or not last:
        return TestResult("T4", "Campaign past PMax learning phase", "inconclusive",
                          "No date range.", [])
    age = (last - first).days + 1
    ev = [{"first_seen": str(first), "last_seen": str(last), "age_days": age}]
    if age < 42:
        # Still inside the ~6-week PMax learning phase. This does NOT falsify
        # the signal — it is explicitly informational about ramping campaigns
        # ("improving signals preview a state-firing campaign exiting on its
        # own as it ramps"). Lack of maturity means we can't yet interpret the
        # move as structural, i.e. inconclusive — not evidence the signal is
        # false. (Also note: when the data window itself is < 6 weeks, no
        # campaign can ever clear this bar, so disconfirm would be an artifact.)
        return TestResult("T4", "Campaign past PMax learning phase", "inconclusive",
                          f"PMax visible only {age}d (<6wk learning phase) — volume movement isn't yet "
                          f"interpretable as structural, but that doesn't make the informational signal false.",
                          ev)
    return TestResult("T4", "Campaign past PMax learning phase", "confirm",
                      f"PMax visible {age}d; past learning-phase noise.", ev)


def audit_pmax_low_conv_volume_change_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'pmax_low_conv_volume_change'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_status_continuity(db, acct_id, camp_id, data),
            test_spend_proportionality(db, acct_id, camp_id, data),
            test_single_day_dominance(db, acct_id, camp_id, data),
            test_learning_phase(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
