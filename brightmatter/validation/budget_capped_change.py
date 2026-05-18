"""Disconfirmation harness for `detect_budget_capped_change`.

Detector claim: avg(search_budget_lost_is) moved by ≥10pp between a recent
14d window and the prior 14d. The signal is informational — direction
(worsening / improving) is in data['direction'].

False-positive shapes the tests look for:
  T1 — Either window had too few days of valid data to support an average
  T2 — Bidding strategy or campaign type changed mid-comparison
  T3 — The "budget" framing hides a rank-loss shift (parent's same concern)
  T4 — A daily-budget change explains the delta as intentional, not pathological
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult


def _windows(data: dict) -> tuple[str, int]:
    return data.get("anchor_date") or "", int(data.get("window_days") or 14)


def test_window_data_sufficiency(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T1", "Window data sufficiency", "inconclusive",
                          "Signal missing anchor_date; cannot recompute.", [])
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
    cur_days, prior_days = (row or (0, 0))
    ev = [{"current_days_with_data": cur_days, "prior_days_with_data": prior_days,
           "window_days": window}]
    if cur_days < 7 or prior_days < 7:
        return TestResult("T1", "Window data sufficiency", "disconfirm",
                          f"Only {cur_days}/{window} cur and {prior_days}/{window} prior days have search_budget_lost_is — average comparison is thin.",
                          ev)
    if cur_days >= 10 and prior_days >= 10:
        return TestResult("T1", "Window data sufficiency", "confirm",
                          f"{cur_days}/{prior_days} days of valid data — comparison is well-supported.",
                          ev)
    return TestResult("T1", "Window data sufficiency", "inconclusive",
                      f"Borderline coverage ({cur_days}/{prior_days} days).", ev)


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
          AND date > DATE '{anchor}' - {2 * window}
          AND date <= DATE '{anchor}'
        """,
        [account_id, campaign_id],
    )
    ev = [{"campaign_type": r[0], "bidding_strategy": r[1]} for r in rows]
    if len(rows) > 1:
        return TestResult("T2", "Bidding / campaign-type stability", "disconfirm",
                          f"{len(rows)} distinct (type, strategy) combos across the 2x window — config shift may explain the delta.",
                          ev)
    return TestResult("T2", "Bidding / campaign-type stability", "confirm",
                      "Campaign type + bidding strategy stable across both windows.", ev)


def test_rank_vs_budget_share(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """If rank-lost-IS shifted more than budget-lost-IS, the 'budget' framing is misleading.

    Same concern as the parent state-detector's T2 but evaluated on the delta.
    """
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T3", "Rank-vs-budget delta share", "inconclusive",
                          "No anchor_date on signal.", [])
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
                          "Could not compute rank vs budget shares.", [])
    cbl, pbl, crl, prl = ((row[0] or 0), (row[1] or 0), (row[2] or 0), (row[3] or 0))
    bl_delta = cbl - pbl
    rl_delta = crl - prl
    ev = [{"budget_lost_delta": round(bl_delta, 3), "rank_lost_delta": round(rl_delta, 3)}]
    if abs(rl_delta) > abs(bl_delta) + 0.05:
        return TestResult("T3", "Rank-vs-budget delta share", "disconfirm",
                          f"Rank-lost moved {rl_delta:+.0%} vs budget-lost {bl_delta:+.0%} — 'budget' framing oversells the budget mechanism.",
                          ev)
    return TestResult("T3", "Rank-vs-budget delta share", "confirm",
                      f"Budget-lost delta ({bl_delta:+.0%}) ≥ rank-lost delta ({rl_delta:+.0%}); budget framing is fair.",
                      ev)


def test_daily_budget_change(db: Database, account_id: str, campaign_id: str, data: dict) -> TestResult:
    """A daily-budget change during the comparison explains the delta as intentional."""
    anchor, window = _windows(data)
    if not anchor:
        return TestResult("T4", "Daily-budget stability", "inconclusive",
                          "No anchor_date on signal.", [])
    rows = db.fetchall(
        f"""
        SELECT count(DISTINCT daily_budget_micros) as distinct_budgets,
               min(daily_budget_micros) as min_b,
               max(daily_budget_micros) as max_b
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date > DATE '{anchor}' - {2 * window} AND date <= DATE '{anchor}'
          AND daily_budget_micros IS NOT NULL AND daily_budget_micros > 0
        """,
        [account_id, campaign_id],
    )
    if not rows or rows[0][0] in (0, None):
        return TestResult("T4", "Daily-budget stability", "inconclusive",
                          "No daily_budget_micros recorded for the window.", [])
    n, min_b, max_b = rows[0]
    ev = [{"distinct_daily_budgets": n,
           "min_budget": (min_b or 0) / 1_000_000,
           "max_budget": (max_b or 0) / 1_000_000}]
    if n >= 2 and max_b and min_b and (max_b / max(min_b, 1)) >= 1.25:
        return TestResult("T4", "Daily-budget stability", "disconfirm",
                          f"Daily budget changed by {((max_b/min_b)-1)*100:.0f}% across the window — the delta reflects an intentional budget action.",
                          ev)
    return TestResult("T4", "Daily-budget stability", "confirm",
                      "Daily budget stable across both windows — delta isn't budget-action noise.",
                      ev)


def audit_budget_capped_change_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'budget_capped_change'
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
            test_daily_budget_change(db, acct_id, camp_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
