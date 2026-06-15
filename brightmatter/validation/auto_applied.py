"""Disconfirmation harness for `detect_auto_applied_changes`.

Detector claim (CONFIRMED tier): Google's recommendation system auto-applied
>= 5 changes to this account in the last 30 days — a direct change-history
log, not an inference. The actionable framing is "review these and opt out of
recommendation types that don't fit your strategy."

Whether the changes HELPED or HURT performance is explicitly unknowable from
Google Ads data (see the confidence framework), so this harness does NOT try
to confirm impact — that would disconfirm a factual signal for failing an
unprovable test. Instead it validates the fact and its review-worthiness:
  T1 — the volume is material (not a couple of trivial tweaks)
  T2 — the changes touch substantive resources (targeting/budget/bids/ads)
  T3 — Google is a primary actor (high share of all account changes)
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed

# Resource types that change what runs, spends, or is bid on — i.e. the kind of
# auto-applied change actually worth a human review (vs cosmetic asset tweaks).
_SUBSTANTIVE = {
    "CAMPAIGN", "CAMPAIGN_BUDGET", "CAMPAIGN_CRITERION", "AD_GROUP",
    "AD_GROUP_CRITERION", "AD_GROUP_AD", "AD", "BIDDING_STRATEGY",
}


def test_volume_material(account_id: str, data: dict) -> TestResult:
    n = int(data.get("count") or 0)
    ev = [{"auto_applied_count": n}]
    if n >= 10:
        return TestResult("T1", "Auto-change volume material", "confirm",
                          f"{n} auto-applied changes in 30d — a material surface that warrants review.", ev)
    if n < 5:
        return TestResult("T1", "Auto-change volume material", "disconfirm",
                          f"Only {n} auto-applied change(s) — below the review-worthy floor.", ev)
    return TestResult("T1", "Auto-change volume material", "inconclusive",
                      f"{n} changes — moderate volume.", ev)


def test_substantive_surface(db: Database, account_id: str) -> TestResult:
    """Do the auto-applied changes touch real structure (targeting/budget/bids/
    ads), or only cosmetic assets? Cosmetic-only is less worth a review."""
    anchor = anchor_date(db)
    rows = db.fetchall(
        windowed("""
        SELECT resource_type, count(*) FROM change_events
        WHERE account_id = ? AND actor = 'auto_applied'
          AND change_timestamp >= current_date - 30
        GROUP BY resource_type
        """, anchor),
        [account_id],
    )
    total = sum(c for _, c in rows)
    sub = sum(c for rt, c in rows if rt in _SUBSTANTIVE)
    share = sub / total if total else 0
    ev = [{"substantive": sub, "total": total, "substantive_share": round(share, 2)}]
    if not total:
        return TestResult("T2", "Substantive change surface", "inconclusive",
                          "No change rows found.", ev)
    if share >= 0.5:
        return TestResult("T2", "Substantive change surface", "confirm",
                          f"{share:.0%} of auto-applied changes touch targeting/budget/bids/ads — substantive, worth review.", ev)
    if share < 0.2:
        return TestResult("T2", "Substantive change surface", "disconfirm",
                          f"Only {share:.0%} touch substantive resources — mostly cosmetic asset tweaks; lower review priority.", ev)
    return TestResult("T2", "Substantive change surface", "inconclusive",
                      f"{share:.0%} substantive — mixed.", ev)


def test_google_is_primary_actor(db: Database, account_id: str) -> TestResult:
    """If Google auto-applies most of the account's changes, the opt-out review
    is clearly warranted. If a human drives most changes, it's less urgent."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        SELECT count(*) FILTER (WHERE actor = 'auto_applied') as auto,
               count(*) as total
        FROM change_events
        WHERE account_id = ? AND change_timestamp >= current_date - 30
        """, anchor),
        [account_id],
    )
    auto, total = (row or (0, 0))
    auto, total = (auto or 0, total or 0)
    share = auto / total if total else 0
    ev = [{"auto_applied": auto, "total_changes": total, "auto_share": round(share, 2)}]
    if share >= 0.5:
        return TestResult("T3", "Google is a primary actor", "confirm",
                          f"{share:.0%} of all recent changes were auto-applied — Google is driving the account; opt-out review is warranted.", ev)
    return TestResult("T3", "Google is a primary actor", "inconclusive",
                      f"{share:.0%} of changes are auto-applied — a human drives most changes here; lower urgency.", ev)


def audit_auto_applied_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
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
            test_volume_material(acct_id, data),
            test_substantive_surface(db, acct_id),
            test_google_is_primary_actor(db, acct_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
