"""Disconfirmation harness for `detect_budget_limited_is_change`.

Detector claim: avg(search_budget_lost_is) moved ≥10pp between a recent 7d
window and the prior 7d, on campaigns with ≥$250 spend in the recent window.
Signal is informational; direction in data['direction'].

False-positive shapes:
  T1 — Sparse data in one window
  T2 — Bidding strategy or campaign type changed mid-comparison
  T3 — Rank-loss is what actually moved (budget framing misleads)
  T4 — Spend collapsed in one window (delta is a near-zero-impression artifact)
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def _windows(data: dict) -> tuple[str, int]:
    return data.get("anchor_date") or "", int(data.get("window_days") or 7)


def test_window_data_sufficiency(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T1", "Window data sufficiency", "inconclusive",
                          "Signal missing anchor_date.", [])
    row = db.fetchone(
        f"""
        SELECT
          count(CASE WHEN date > DATE '{anchor}' - {window}
                      AND date <= DATE '{anchor}'
                      AND search_budget_lost_is IS NOT NULL THEN 1 END) as cur_days,
          count(CASE WHEN date > DATE '{anchor}' - {2 * window}
                      AND date <= DATE '{anchor}' - {window}
                      AND search_budget_lost_is IS NOT NULL THEN 1 END) as prior_days
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
        """,
        [account_id, campaign_id],
    )
    cur, prior = (row or (0, 0))
    ev = [{"current_days_with_data": cur, "prior_days_with_data": prior, "window_days": window}]
    if cur < 5 or prior < 5:
        return TestResult("T1", "Window data sufficiency", "disconfirm",
                          f"Only {cur}/{window} cur, {prior}/{window} prior days have data — too thin.",
                          ev)
    if cur >= 6 and prior >= 6:
        return TestResult("T1", "Window data sufficiency", "confirm",
                          f"{cur}/{prior} days of data — comparison well-supported.", ev)
    return TestResult("T1", "Window data sufficiency", "inconclusive",
                      f"Borderline coverage ({cur}/{prior}).", ev)


def test_config_stability(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T2", "Bidding / campaign-type stability", "inconclusive",
                          "No anchor_date on signal.", [])
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
        return TestResult("T2", "Bidding / campaign-type stability", "disconfirm",
                          f"{len(rows)} distinct (type, strategy) combos — config shift may explain the delta.",
                          ev)
    return TestResult("T2", "Bidding / campaign-type stability", "confirm",
                      "Type + strategy stable across both windows.", ev)


def test_rank_vs_budget_share(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T3", "Rank-vs-budget delta share", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT avg(search_budget_lost_is) as bl, avg(search_rank_lost_is) as rl
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT avg(search_budget_lost_is) as bl, avg(search_rank_lost_is) as rl
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        )
        SELECT cur.bl, prior.bl, cur.rl, prior.rl FROM cur, prior
        """,
        [account_id, campaign_id, account_id, campaign_id],
    )
    if not row:
        return TestResult("T3", "Rank-vs-budget delta share", "inconclusive",
                          "Insufficient data.", [])
    cbl, pbl, crl, prl = ((row[0] or 0), (row[1] or 0), (row[2] or 0), (row[3] or 0))
    bl_delta, rl_delta = cbl - pbl, crl - prl
    ev = [{"budget_lost_delta": round(bl_delta, 3), "rank_lost_delta": round(rl_delta, 3)}]
    if abs(rl_delta) > abs(bl_delta) + 0.05:
        return TestResult("T3", "Rank-vs-budget delta share", "disconfirm",
                          f"Rank-lost moved {rl_delta:+.0%} vs budget-lost {bl_delta:+.0%} — 'budget' framing oversells.",
                          ev)
    return TestResult("T3", "Rank-vs-budget delta share", "confirm",
                      f"Budget-lost delta ({bl_delta:+.0%}) dominates rank ({rl_delta:+.0%}).",
                      ev)


def test_spend_continuity(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """A spend collapse in one window makes the IS-lost metric meaningless on that side."""
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T4", "Spend continuity across windows", "inconclusive",
                          "No anchor_date.", [])
    row = db.fetchone(
        f"""
        WITH cur AS (
          SELECT sum(cost_micros) / 1000000.0 as cost
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {window} AND date <= DATE '{anchor}'
        ),
        prior AS (
          SELECT sum(cost_micros) / 1000000.0 as cost
          FROM daily_metrics
          WHERE account_id = ? AND campaign_id = ?
            AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}' - {window}
        )
        SELECT cur.cost, prior.cost FROM cur, prior
        """,
        [account_id, campaign_id, account_id, campaign_id],
    )
    cur_cost, prior_cost = (row or (0, 0))
    cur_cost, prior_cost = (cur_cost or 0, prior_cost or 0)
    ev = [{"current_spend_usd": round(cur_cost, 2), "prior_spend_usd": round(prior_cost, 2)}]
    if cur_cost < 50 or prior_cost < 50:
        return TestResult("T4", "Spend continuity across windows", "disconfirm",
                          f"Spend was ${cur_cost:.0f} cur / ${prior_cost:.0f} prior — IS-lost on a near-dark window is unreliable.",
                          ev)
    ratio = max(cur_cost, prior_cost) / max(min(cur_cost, prior_cost), 1)
    if ratio >= 4.0:
        return TestResult("T4", "Spend continuity across windows", "disconfirm",
                          f"Spend ratio {ratio:.1f}x between windows — the campaign was effectively a different size; IS-lost delta is not apples-to-apples.",
                          ev)
    return TestResult("T4", "Spend continuity across windows", "confirm",
                      f"Spend comparable across windows (${prior_cost:.0f} → ${cur_cost:.0f}).",
                      ev)


def audit_budget_limited_is_change_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'budget_limited_is_change'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_window_data_sufficiency(db, acct_id, camp_id, data),
            test_config_stability(db, acct_id, camp_id, data),
            test_rank_vs_budget_share(db, acct_id, camp_id, data),
            test_spend_continuity(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
