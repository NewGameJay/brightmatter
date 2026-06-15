"""Disconfirmation harness for `detect_search_terms_waste`.

Detector claim: a material share of a campaign's spend went to search terms
that never converted over the window — wasted spend to negative-out.

SCAFFOLDED 2026-06 alongside the detector. It produces no audits until the
search_terms table is populated (ingest --search-terms); validate the
thresholds against real search-term data on the first ingest.

Disconfirmation tests:
  T1 — the "wasted" terms had too few clicks to confidently call non-converting
  T2 — the waste is an immaterial share of campaign spend (marginal trigger)
  T3 — assisted-conversion blind spot: last-click search-term data can't see
       assists, so a campaign that converts well elsewhere may be getting
       top-of-funnel help from these terms (surfaced as caveat, not a kill)
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_click_sufficiency(db: Database, data: dict) -> TestResult:
    clicks = data.get("waste_clicks") or 0
    ev = [{"waste_clicks": clicks, "waste_terms": data.get("waste_terms")}]
    if clicks < 20:
        return TestResult("T1", "Wasted-term click sufficiency", "disconfirm",
                          f"Zero-conversion terms drew only {clicks:.0f} clicks — too little traffic to be confident they never convert (noise).",
                          ev)
    if clicks >= 50:
        return TestResult("T1", "Wasted-term click sufficiency", "confirm",
                          f"{clicks:.0f} clicks on zero-conversion terms — enough traffic that the lack of conversions is a real signal.",
                          ev)
    return TestResult("T1", "Wasted-term click sufficiency", "inconclusive",
                      f"{clicks:.0f} clicks — borderline confidence.", ev)


def test_share_materiality(db: Database, data: dict) -> TestResult:
    share = data.get("waste_share") or 0
    ev = [{"waste_share": round(share, 3), "waste_cost": data.get("waste_cost")}]
    if share >= 0.30:
        return TestResult("T2", "Waste share materiality", "confirm",
                          f"{share:.0%} of campaign spend went to zero-converting terms — a systemic leak.",
                          ev)
    if share < 0.15:
        return TestResult("T2", "Waste share materiality", "disconfirm",
                          f"Only {share:.0%} of spend — marginal; a few stray terms, not a structural problem.",
                          ev)
    return TestResult("T2", "Waste share materiality", "inconclusive",
                      f"{share:.0%} of spend — moderate.", ev)


def test_assisted_conversion_caveat(db: Database, account_id: str, campaign_id: str) -> TestResult:
    """Search-term data is last-click; it can't show whether these terms assisted
    conversions credited elsewhere. If the campaign converts well overall, treat
    the waste claim cautiously; if it barely converts, the waste stands."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT sum(conversions) as conv, sum(clicks) as clicks
        FROM daily_metrics
        WHERE account_id = ? AND campaign_id = ? AND date >= current_date - 30
        """, anchor),
        [account_id, campaign_id],
    )
    conv, clicks = (row or (0, 0))
    conv, clicks = (conv or 0, clicks or 0)
    cvr = (conv / clicks) if clicks else 0
    ev = [{"campaign_cvr_30d": round(cvr, 4), "campaign_conv_30d": conv}]
    if conv < 5:
        return TestResult("T3", "Assisted-conversion caveat", "confirm",
                          f"Campaign itself barely converts ({conv:.0f} conv/30d) — the flagged terms aren't plausibly assisting hidden conversions.",
                          ev)
    if cvr >= 0.05:
        return TestResult("T3", "Assisted-conversion caveat", "disconfirm",
                          f"Campaign converts well overall (CVR {cvr:.1%}) — some 'wasted' terms may assist conversions credited to other terms (last-click blind spot).",
                          ev)
    return TestResult("T3", "Assisted-conversion caveat", "inconclusive",
                      f"Campaign CVR {cvr:.1%} — can't rule assists in or out from last-click data.", ev)


def audit_search_terms_waste_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.campaign_id, s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'search_terms_waste'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, camp_id, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_click_sufficiency(db, data),
            test_share_materiality(db, data),
            test_assisted_conversion_caveat(db, acct_id, camp_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            campaign_id=camp_id, detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
