"""Disconfirmation harness for `detect_impression_share_loss` (budget_limited_is).

Detector claim: a campaign losing >35% impression share to budget represents
an under-spending opportunity — implicit causal claim is "more budget would
mean more conversions."

Tests below try to disconfirm that causal claim using adjacent observations.
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


# ── Tests ──

def test_rank_loss_dominance(account_id: str, campaign_id: str, data: dict) -> TestResult:
    """T1 — If rank-lost-IS exceeds budget-lost-IS, the bottleneck isn't budget.

    Geddes/Lolk consensus: you can't outbid quality. Adding budget when rank
    loss dominates won't produce conversions; only bid/QS work will.
    """
    bl = data.get("budget_lost_is") or 0
    rl = data.get("rank_lost_is") or 0
    ev = [{"budget_lost_is": round(bl, 3), "rank_lost_is": round(rl, 3)}]
    if rl > bl + 0.05:
        return TestResult(
            "T1", "Budget vs rank loss dominance", "disconfirm",
            f"Rank loss ({rl:.0%}) exceeds budget loss ({bl:.0%}) — bid/QS is the bottleneck, not budget.",
            ev,
        )
    if bl > rl + 0.10:
        return TestResult(
            "T1", "Budget vs rank loss dominance", "confirm",
            f"Budget loss ({bl:.0%}) clearly dominates rank loss ({rl:.0%}); budget is the binding constraint.",
            ev,
        )
    return TestResult(
        "T1", "Budget vs rank loss dominance", "inconclusive",
        f"Budget and rank losses are similar ({bl:.0%} vs {rl:.0%}); both contribute.",
        ev,
    )


def test_cpa_plausibility(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """T2 — If campaign CPA is already very high, uncapping budget will burn cash.

    Disconfirms the implicit "more budget → more conversions" by showing the
    cost-per-conversion is in a range that wouldn't survive scale.
    """
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(cost_micros)/1000000.0 as cost,
               sum(conversions) as conv,
               sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 30
        """, anchor),
        [account_id, campaign_id],
    )
    cost, conv, clicks = (row or (0, 0, 0))
    cost = cost or 0
    conv = conv or 0
    if conv < 1:
        return TestResult(
            "T2", "Campaign CPA plausibility", "disconfirm",
            f"Campaign has {conv:.1f} conversions in 30d on ${cost:,.0f} spend — CPA is undefined; uncapping budget is unsupported.",
            [{"cost_30d": cost, "conversions_30d": conv, "clicks_30d": clicks}],
        )
    cpa = cost / conv
    ev = [{"cost_30d": round(cost, 2), "conversions_30d": conv, "cpa_30d": round(cpa, 2)}]
    if cpa > 500:
        return TestResult(
            "T2", "Campaign CPA plausibility", "disconfirm",
            f"Campaign CPA is ${cpa:,.0f} — uncapping budget at this CPA scales loss, not value.",
            ev,
        )
    if cpa <= 200:
        return TestResult(
            "T2", "Campaign CPA plausibility", "confirm",
            f"CPA ${cpa:,.0f} is in a range where additional budget plausibly produces conversions.",
            ev,
        )
    return TestResult(
        "T2", "Campaign CPA plausibility", "inconclusive",
        f"CPA ${cpa:,.0f} is mid-range; needs vertical/tier benchmark to judge.",
        ev,
    )


def test_volume_sufficiency(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """T3 — Without enough conversions, "budget-limited" is unverifiable."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) as conv, sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 7
        """, anchor),
        [account_id, campaign_id],
    )
    conv, clicks = (row or (0, 0))
    conv = conv or 0
    clicks = clicks or 0
    ev = [{"conversions_7d": conv, "clicks_7d": clicks}]
    if conv < 5:
        return TestResult(
            "T3", "Conversion volume sufficiency", "disconfirm",
            f"Only {conv:.0f} conversions in 7d ({clicks} clicks) — claim of budget-limited growth is unsupported by data.",
            ev,
        )
    if conv >= 20:
        return TestResult(
            "T3", "Conversion volume sufficiency", "confirm",
            f"{conv:.0f} conversions in 7d — enough volume to credibly claim more budget would scale.",
            ev,
        )
    return TestResult(
        "T3", "Conversion volume sufficiency", "inconclusive",
        f"{conv:.0f} conversions in 7d — borderline; signal is suggestive but not strongly grounded.",
        ev,
    )


def test_budget_set_low_intentionally(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """T4 — If daily_budget is far below the account's typical campaign budget,
    the campaign may be intentionally throttled, not undercapitalized."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT avg(daily_budget_micros)/1000000.0 as this_budget,
               (SELECT median(daily_budget_micros)/1000000.0
                  FROM daily_metrics
                  WHERE account_id = ? AND date >= current_date - 30
                    AND daily_budget_micros IS NOT NULL) as account_median
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ?
          AND date >= current_date - 7
          AND daily_budget_micros IS NOT NULL
        """, anchor),
        [account_id, account_id, campaign_id],
    )
    this_b, median_b = (row or (None, None))
    if this_b is None or median_b is None or median_b == 0:
        return TestResult(
            "T4", "Budget vs account-typical", "inconclusive",
            "Insufficient budget data to compare against account median.",
        )
    ratio = this_b / median_b
    ev = [{"this_campaign_budget": round(this_b, 2),
           "account_median_budget": round(median_b, 2),
           "ratio": round(ratio, 2)}]
    if ratio < 0.4:
        return TestResult(
            "T4", "Budget vs account-typical", "disconfirm",
            f"Campaign budget is {ratio:.0%} of account median — likely intentionally throttled, not under-funded.",
            ev,
        )
    if ratio >= 0.7:
        return TestResult(
            "T4", "Budget vs account-typical", "confirm",
            f"Campaign budget is {ratio:.0%} of account median — within normal range; cap is real.",
            ev,
        )
    return TestResult(
        "T4", "Budget vs account-typical", "inconclusive",
        f"Campaign budget is {ratio:.0%} of account median — ambiguous.",
        ev,
    )


# ── Orchestration ──

def audit_budget_limited_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    """Run the harness against budget_limited_is signals (newest first)."""
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'budget_limited_is'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits: list[SignalAudit] = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_rank_loss_dominance(acct_id, camp_id, data),
            test_cpa_plausibility(db, acct_id, camp_id),
            test_volume_sufficiency(db, acct_id, camp_id),
            test_budget_set_low_intentionally(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
