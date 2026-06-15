"""Disconfirmation harness for `detect_pmax_conversion_inflation`.

Detector claim: within one account, PMax CVR is ≥3x Search CVR over 30 days,
suggesting PMax is counting conversion actions Search isn't (micro-conversion
inflation).

Disconfirmation tests probe the alternative explanations:
  T1 — the gap is small-sample noise (thin volume on either channel)
  T2 — no inflation *mechanism*: all primaries are legit, one-per-click goals
  T3 — PMax & Search value-per-conversion match (conversions are equally real)
  T4 — the anomaly is a depressed Search baseline, not an inflated PMax
"""

from __future__ import annotations

import json

from brightmatter.analysis.detectors import _SUSPICIOUS_CATEGORIES
from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


def test_volume_reliability(db: Database, account_id: str, data: dict) -> TestResult:
    pconv = data.get("pmax_conv") or 0
    sconv = data.get("search_conv") or 0
    ev = [{"pmax_conv": pconv, "search_conv": sconv}]
    if pconv < 15 or sconv < 5:
        return TestResult("T1", "Volume reliability", "disconfirm",
                          f"Thin volume (PMax {pconv:.0f} / Search {sconv:.0f} conv) — the CVR ratio is small-sample noise.",
                          ev)
    return TestResult("T1", "Volume reliability", "confirm",
                      f"Both channels have enough conversions (PMax {pconv:.0f} / Search {sconv:.0f}) for the ratio to be stable.",
                      ev)


def test_inflation_mechanism(db: Database, account_id: str) -> TestResult:
    """Is there a mechanism that could inflate PMax conversions — micro-conversion
    primaries or many-per-click counting? Without one, a high PMax CVR is more
    likely real shopping intent than inflated counting."""
    rows = db.fetchall(
        """
        SELECT category, counting_type, count(*) as n
        FROM conversion_actions
        WHERE account_id = ? AND primary_for_goal = true AND status = 'ENABLED'
        GROUP BY category, counting_type
        """,
        [account_id],
    )
    micro = [(c, ct, n) for c, ct, n in rows if c in _SUSPICIOUS_CATEGORIES]
    many = [(c, ct, n) for c, ct, n in rows if ct == "MANY_PER_CLICK"]
    ev = [{"primary_actions": [(c, ct, n) for c, ct, n in rows]}]
    if not rows:
        return TestResult("T2", "Inflation mechanism present", "inconclusive",
                          "No ENABLED primary conversion actions found for the account.", ev)
    if micro or many:
        bits = []
        if micro:
            bits.append(f"{sum(n for *_, n in micro)} micro-conversion primaries ({', '.join(c for c, _, _ in micro)})")
        if many:
            bits.append(f"{sum(n for *_, n in many)} many-per-click primaries")
        return TestResult("T2", "Inflation mechanism present", "confirm",
                          f"Account has a mechanism that inflates counts: {'; '.join(bits)}.",
                          ev)
    return TestResult("T2", "Inflation mechanism present", "disconfirm",
                      "All ENABLED primaries are legit, one-per-click goals — no micro-conversion mechanism; high PMax CVR may be genuine intent.",
                      ev)


def test_value_per_conversion_gap(db: Database, account_id: str, data: dict) -> TestResult:
    """If PMax and Search conversions are worth about the same, the PMax
    conversions are probably as real as Search's. A much lower PMax value per
    conversion is the fingerprint of cheap/micro conversions padding the count."""
    pvpc = data.get("pmax_value_per_conv")
    svpc = data.get("search_value_per_conv")
    ev = [{"pmax_value_per_conv": pvpc, "search_value_per_conv": svpc}]
    if not pvpc or not svpc:
        return TestResult("T3", "Value-per-conversion gap", "inconclusive",
                          "Missing conversion-value on one channel — can't compare worth.", ev)
    ratio = pvpc / svpc if svpc else 0
    if ratio < 0.5:
        return TestResult("T3", "Value-per-conversion gap", "confirm",
                          f"PMax value/conv (${pvpc:,.2f}) is {ratio:.0%} of Search's (${svpc:,.2f}) — PMax conversions are worth far less, consistent with counting cheaper actions.",
                          ev)
    if ratio >= 0.8:
        return TestResult("T3", "Value-per-conversion gap", "disconfirm",
                          f"PMax value/conv (${pvpc:,.2f}) ≈ Search's (${svpc:,.2f}) — conversions are worth about the same, so they're likely equally real.",
                          ev)
    return TestResult("T3", "Value-per-conversion gap", "inconclusive",
                      f"PMax value/conv is {ratio:.0%} of Search — moderate gap, ambiguous.", ev)


def test_search_baseline_sane(db: Database, account_id: str, data: dict) -> TestResult:
    """A high ratio can mean PMax is inflated OR Search is unusually weak. If the
    PMax CVR itself is implausibly high, inflation is the better explanation; if
    PMax CVR is normal and Search is just depressed, the anomaly isn't PMax."""
    pcvr = data.get("pmax_cvr") or 0
    scvr = data.get("search_cvr") or 0
    ev = [{"pmax_cvr": round(pcvr, 4), "search_cvr": round(scvr, 4)}]
    if pcvr > 0.50:
        return TestResult("T4", "PMax CVR plausibility", "confirm",
                          f"PMax CVR {pcvr:.0%} is implausibly high for genuine purchases/leads — points to inflated counting.",
                          ev)
    if pcvr < 0.10 and scvr < 0.03:
        return TestResult("T4", "PMax CVR plausibility", "disconfirm",
                          f"PMax CVR is modest ({pcvr:.1%}); the ratio is high mainly because Search CVR is very low ({scvr:.1%}) — the anomaly may be Search, not PMax inflation.",
                          ev)
    return TestResult("T4", "PMax CVR plausibility", "inconclusive",
                      f"PMax CVR {pcvr:.1%} vs Search {scvr:.1%} — elevated but not extreme.", ev)


def audit_pmax_conversion_inflation_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'pmax_conversion_inflation'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_volume_reliability(db, acct_id, data),
            test_inflation_mechanism(db, acct_id),
            test_value_per_conversion_gap(db, acct_id, data),
            test_search_baseline_sane(db, acct_id, data),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
