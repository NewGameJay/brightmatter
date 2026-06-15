"""Disconfirmation harness for `detect_budget_capped_campaigns`.

Detector claim: campaign is consistently hitting its budget cap (avg
search_budget_lost_is > 30% across 7+ of last 14 days). Weaker than
budget_limited_is — it's an observation, not a recommendation. Tests focus
on whether the cap is real, intentional, or noise.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_actual_spend_at_cap(db: Database, account_id: str, campaign_id: str) -> TestResult:
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT avg(cost_micros / NULLIF(daily_budget_micros, 0)) as utilization
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 14
          AND daily_budget_micros IS NOT NULL AND daily_budget_micros > 0
        """, anchor),
        [account_id, campaign_id],
    )
    util = (row[0] if row and row[0] is not None else None)
    ev = [{"avg_budget_utilization": round(util, 3) if util is not None else None}]
    if util is None:
        return TestResult("T1", "Spend-at-cap reality check", "inconclusive",
                          "No daily_budget_micros available to verify cap.", ev)
    if util >= 0.85:
        return TestResult("T1", "Spend-at-cap reality check", "confirm",
                          f"Avg daily utilization {util:.0%} — budget really is the binding constraint.", ev)
    if util < 0.50:
        return TestResult("T1", "Spend-at-cap reality check", "disconfirm",
                          f"Avg daily utilization only {util:.0%} — budget_lost_is may reflect rank/quality, not actual cap.", ev)
    return TestResult("T1", "Spend-at-cap reality check", "inconclusive",
                      f"Mid-range utilization ({util:.0%}); ambiguous.", ev)


def test_rank_loss_share(db: Database, account_id: str, campaign_id: str) -> TestResult:
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT avg(search_budget_lost_is) as bl, avg(search_rank_lost_is) as rl
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 14
          AND search_budget_lost_is IS NOT NULL
        """, anchor),
        [account_id, campaign_id],
    )
    bl, rl = (row or (0, 0))
    bl, rl = (bl or 0, rl or 0)
    ev = [{"avg_budget_lost_is": round(bl, 3), "avg_rank_lost_is": round(rl, 3)}]
    if rl > bl + 0.10:
        return TestResult("T2", "Rank-loss share check", "disconfirm",
                          f"Rank loss ({rl:.0%}) exceeds budget loss ({bl:.0%}); 'capped' framing misleads — quality is the real bottleneck.", ev)
    return TestResult("T2", "Rank-loss share check", "confirm",
                      f"Budget loss {bl:.0%} ≥ rank loss {rl:.0%}; budget cap framing is fair.", ev)


def test_volume_sufficiency(db: Database, account_id: str, campaign_id: str) -> TestResult:
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) as conv
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 14
        """, anchor),
        [account_id, campaign_id],
    )
    conv = (row[0] if row else 0) or 0
    ev = [{"conversions_14d": conv}]
    if conv < 5:
        return TestResult("T3", "Conversion volume sufficiency", "disconfirm",
                          f"Only {conv:.0f} convs in 14d — 'capped growth' assumes uplift; can't be claimed at this volume.", ev)
    if conv >= 15:
        return TestResult("T3", "Conversion volume sufficiency", "confirm",
                          f"{conv:.0f} convs in 14d — enough for 'budget caps growth' to be meaningful.", ev)
    return TestResult("T3", "Conversion volume sufficiency", "inconclusive",
                      f"{conv:.0f} convs in 14d — borderline.", ev)


def audit_budget_capped_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'budget_capped'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_actual_spend_at_cap(db, acct_id, camp_id),
            test_rank_loss_share(db, acct_id, camp_id),
            test_volume_sufficiency(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
