"""Disconfirmation harness for `detect_cpa_change`.

Detector claim: campaign CPA moved by ≥25% between equal 7d windows.
Bidirectional. The detector already pre-filters the CURRENT window for
≥5 conv, ≥3 active days, and ≤50% single-day share. The harness extends
those checks to the PRIOR window (whose noise can equally distort the
delta) and adds parent-style AOV / bidding-strategy disconfirmation.

False-positive shapes:
  T1 — Prior window itself was noise-dominated (low conv, sparse days)
  T2 — Bidding strategy changed during the comparison
  T3 — AOV movement explains the CPA delta (Smart Bidding buying higher
       or lower value, not changing efficiency)
  T4 — Single-day spend dominance in the PRIOR window (parent already
       enforces this on current)
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def _windows(data: dict) -> tuple[str, int]:
    return data.get("anchor_date") or "", int(data.get("window_days") or 7)


def test_prior_window_volume(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """Mirror of cpa_spike T1, applied to the PRIOR window."""
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T1", "Prior-window volume reliability", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        SELECT sum(conversions) as conv,
               count(DISTINCT CASE WHEN cost_micros > 0 THEN date END) as active_days
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        """,
        [account_id, campaign_id],
    )
    conv, active = (row or (0, 0))
    conv, active = ((conv or 0), (active or 0))
    ev = [{"prior_conversions": conv, "prior_active_days": active}]
    if conv < 5 or active < 3:
        return TestResult("T1", "Prior-window volume reliability", "disconfirm",
                          f"Prior had {conv:.1f} conv / {active} active days — CPA baseline is noise-dominated.",
                          ev)
    if conv >= 15 and active >= 5:
        return TestResult("T1", "Prior-window volume reliability", "confirm",
                          f"Prior had {conv:.0f} conv / {active} active days — reliable baseline.",
                          ev)
    return TestResult("T1", "Prior-window volume reliability", "inconclusive",
                      f"Borderline prior volume ({conv:.0f} conv / {active} days).", ev)


def test_bidding_strategy_stability(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T2", "Bidding-strategy stability", "inconclusive",
                          "No anchor_date.", [])
    rows = db.fetchall(
        f"""
        SELECT DISTINCT bidding_strategy
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}'
          AND bidding_strategy IS NOT NULL
        """,
        [account_id, campaign_id],
    )
    ev = [{"strategies_seen": [r[0] for r in rows]}]
    if len(rows) > 1:
        return TestResult("T2", "Bidding-strategy stability", "disconfirm",
                          f"Strategy changed during the comparison ({len(rows)} distinct values) — CPA delta likely reflects strategy switch.",
                          ev)
    return TestResult("T2", "Bidding-strategy stability", "confirm",
                      "Bidding strategy stable across both windows.", ev)


def test_aov_movement(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """AOV lift/drop explains CPA movement in either direction.

    For 'worsening' (CPA up): if AOV is up proportionally, higher CPA is
    buying higher-value conversions — not a degradation.
    For 'improving' (CPA down): if AOV is down proportionally, lower CPA
    is buying lower-value conversions — not an efficiency win.
    """
    anchor, window = _windows(data)
    direction = data.get("direction") or ""
    if not anchor:
        return TestResult("T3", "AOV movement explains CPA", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT sum(conversion_value) as v, sum(conversions) as c
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT sum(conversion_value) as v, sum(conversions) as c
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        )
        SELECT cur.v, cur.c, prior.v, prior.c FROM cur, prior
        """,
        [account_id, campaign_id, account_id, campaign_id],
    )
    rv, rc, bv, bc = (row or (0, 0, 0, 0))
    rv, rc, bv, bc = (rv or 0, rc or 0, bv or 0, bc or 0)
    if not rc or not bc or not bv:
        return TestResult("T3", "AOV movement explains CPA", "inconclusive",
                          "Insufficient conversion-value data on one side.", [])
    recent_aov = rv / rc
    base_aov = bv / bc
    if not base_aov:
        return TestResult("T3", "AOV movement explains CPA", "inconclusive",
                          "Baseline AOV is zero (no value tracking?).", [])
    lift = recent_aov / base_aov
    ev = [{"recent_aov": round(recent_aov, 2), "base_aov": round(base_aov, 2),
           "aov_lift": round(lift, 2)}]
    if direction == "worsening" and lift >= 1.5:
        return TestResult("T3", "AOV movement explains CPA", "disconfirm",
                          f"AOV rose {lift:.1f}x — higher CPA is buying higher-value conversions, not degraded performance.",
                          ev)
    if direction == "improving" and lift <= 0.67:
        return TestResult("T3", "AOV movement explains CPA", "disconfirm",
                          f"AOV fell to {lift:.1f}x — lower CPA is buying lower-value conversions, not real efficiency.",
                          ev)
    return TestResult("T3", "AOV movement explains CPA", "confirm",
                      f"AOV roughly stable ({lift:.1f}x) — CPA {direction} isn't explained by value movement.",
                      ev)


def test_prior_single_day_share(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """The detector enforces ≤50% single-day spend share on CURRENT only — check the prior side."""
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T4", "Prior single-day spend dominance", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        SELECT max(cost_micros) / NULLIF(sum(cost_micros), 0) as share
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        """,
        [account_id, campaign_id],
    )
    share = (row[0] if row and row[0] is not None else None)
    ev = [{"prior_max_day_spend_share": round(share, 3) if share is not None else None}]
    if share is None:
        return TestResult("T4", "Prior single-day spend dominance", "inconclusive",
                          "No prior-window spend data.", ev)
    if share > 0.50:
        return TestResult("T4", "Prior single-day spend dominance", "disconfirm",
                          f"One day held {share:.0%} of prior-window spend — prior CPA is leveraged on one observation.",
                          ev)
    return TestResult("T4", "Prior single-day spend dominance", "confirm",
                      f"Prior-window spend spread (max-day share {share:.0%}).", ev)


def audit_cpa_change_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'cpa_change'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_prior_window_volume(db, acct_id, camp_id, data),
            test_bidding_strategy_stability(db, acct_id, camp_id, data),
            test_aov_movement(db, acct_id, camp_id, data),
            test_prior_single_day_share(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
