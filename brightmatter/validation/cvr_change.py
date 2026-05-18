"""Disconfirmation harness for `detect_cvr_change`.

Detector claim: campaign CVR moved by ≥15% between equal 7d windows.
Bidirectional — data['direction'] is 'improving' or 'worsening'. Independent
from cvr_drop (which fires on ≥30% drops only).

False-positive shapes:
  T1 — Conversion-tracking change in the comparison window (apparent move
       is measurement, not performance)
  T2 — Campaign type / bidding strategy changed mid-window
  T3 — Direction-specific mean-reversion: for worsening, prior was a
       positive outlier vs broader baseline; for improving, prior was a
       negative outlier
  T4 — Single-day click dominance in either window
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def _windows(data: dict) -> tuple[str, int]:
    return data.get("anchor_date") or "", int(data.get("window_days") or 7)


def test_tracking_change_in_window(db: Database, account_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T1", "Tracking change in window", "inconclusive",
                          "No anchor_date.", [])
    rows = db.fetchall(
        f"""
        SELECT change_timestamp, change_type, resource_type, actor
        FROM change_events
        WHERE account_id = ?
          AND change_timestamp > DATE '{anchor}' - {2 * window}
          AND change_timestamp <= DATE '{anchor}'
          AND (upper(resource_type) LIKE '%CONVERSION%' OR upper(change_type) LIKE '%CONVERSION%')
        ORDER BY change_timestamp DESC
        LIMIT 10
        """,
        [account_id],
    )
    ev = [{"timestamp": str(r[0]), "change_type": r[1],
           "resource_type": r[2], "actor": r[3]} for r in rows]
    if rows:
        return TestResult("T1", "Tracking change in window", "disconfirm",
                          f"{len(rows)} conversion-tracking change(s) inside the 2x{window}d window — CVR delta may be measurement, not performance.",
                          ev)
    return TestResult("T1", "Tracking change in window", "confirm",
                      f"No conversion-tracking changes in the comparison window.", ev)


def test_config_stability(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T2", "Campaign-type / bidding-strategy stability", "inconclusive",
                          "No anchor_date.", [])
    rows = db.fetchall(
        f"""
        SELECT DISTINCT campaign_type, bidding_strategy
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}'
        """,
        [account_id, campaign_id],
    )
    ev = [{"campaign_type": r[0], "bidding_strategy": r[1]} for r in rows]
    if len(rows) > 1:
        return TestResult("T2", "Campaign-type / bidding-strategy stability", "disconfirm",
                          f"{len(rows)} distinct (type, strategy) combos — mix shift may explain the CVR delta.",
                          ev)
    return TestResult("T2", "Campaign-type / bidding-strategy stability", "confirm",
                      "Type + strategy stable across both windows.", ev)


def test_prior_window_anomaly(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """Direction-aware mean-reversion check.

    Look at the two windows BEFORE the prior window (the comparison's
    baseline). For 'worsening' direction: if prior > baseline, the move
    is regression. For 'improving': if prior < baseline, the move is
    regression in reverse.
    """
    anchor, window = _windows(data)
    direction = data.get("direction") or ""
    if not anchor:
        return TestResult("T3", "Prior-window mean-reversion check", "inconclusive",
                          "No anchor_date.", [])
    rows = db.fetchall(
        f"""
        SELECT
          CASE
            WHEN date > DATE '{anchor}' - {window}     THEN 'w1_current'
            WHEN date > DATE '{anchor}' - {2 * window} THEN 'w2_prior'
            WHEN date > DATE '{anchor}' - {3 * window} THEN 'w3_baseline_a'
            WHEN date > DATE '{anchor}' - {4 * window} THEN 'w4_baseline_b'
            ELSE 'older'
          END as bucket,
          sum(conversions) as conv, sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {4 * window} AND date <= DATE '{anchor}'
        GROUP BY 1
        """,
        [account_id, campaign_id],
    )
    by_bucket = {b: (c or 0, k or 0) for b, c, k in rows if b != "older"}
    cvrs = {b: ((c / k) if k else 0) for b, (c, k) in by_bucket.items()}
    prior = cvrs.get("w2_prior", 0)
    baseline = [cvrs.get("w3_baseline_a", 0), cvrs.get("w4_baseline_b", 0)]
    baseline = [b for b in baseline if b > 0]
    ev = [{"weekly_cvrs": {k: round(v, 4) for k, v in cvrs.items()}}]
    if not baseline:
        return TestResult("T3", "Prior-window mean-reversion check", "inconclusive",
                          f"No w3/w4 baseline available for {direction} delta.", ev)
    avg_b = sum(baseline) / len(baseline)
    if direction == "worsening" and avg_b > 0 and prior > avg_b * 1.4:
        return TestResult("T3", "Prior-window mean-reversion check", "disconfirm",
                          f"Prior CVR {prior:.2%} was {prior/avg_b:.1f}x the w3/w4 baseline {avg_b:.2%} — worsening is regression to mean.",
                          ev)
    if direction == "improving" and avg_b > 0 and prior > 0 and prior < avg_b * 0.7:
        return TestResult("T3", "Prior-window mean-reversion check", "disconfirm",
                          f"Prior CVR {prior:.2%} was only {prior/avg_b:.1f}x the w3/w4 baseline {avg_b:.2%} — improvement is regression in reverse.",
                          ev)
    return TestResult("T3", "Prior-window mean-reversion check", "confirm",
                      f"Prior CVR {prior:.2%} consistent with w3/w4 baseline {avg_b:.2%}; the {direction} move is real, not mean reversion.",
                      ev)


def test_single_day_clicks(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T4", "Single-day click dominance", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT max(clicks) / NULLIF(sum(clicks), 0) as share
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT max(clicks) / NULLIF(sum(clicks), 0) as share
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
    ev = [{"cur_max_day_clicks_share": round(cur_share, 3),
           "prior_max_day_clicks_share": round(prior_share, 3)}]
    if max(cur_share, prior_share) > 0.50:
        return TestResult("T4", "Single-day click dominance", "disconfirm",
                          f"One day held >50% of clicks in {'current' if cur_share > prior_share else 'prior'} window — CVR is dominated by one day.",
                          ev)
    return TestResult("T4", "Single-day click dominance", "confirm",
                      f"Clicks spread across windows (max-day shares {prior_share:.0%} / {cur_share:.0%}).",
                      ev)


def audit_cvr_change_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'cvr_change'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_tracking_change_in_window(db, acct_id, data),
            test_config_stability(db, acct_id, camp_id, data),
            test_prior_window_anomaly(db, acct_id, camp_id, data),
            test_single_day_clicks(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
