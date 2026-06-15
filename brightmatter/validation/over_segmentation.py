"""Disconfirmation harness for `detect_over_segmentation`.

Detector claim: ≥50% of campaigns have <30 conv/month — too many small
campaigns starving for data; consolidate.

Common false positives: intentional geo splits, brand/non-brand splits,
campaign-type splits (Search + PMax + Shopping), and recently-launched
campaigns that haven't ramped yet.
"""

from __future__ import annotations

import json
import re

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, anchor_date, windowed


_GEO_HINTS = re.compile(
    r"\b(usa|us|uk|ca|eu|au|de|fr|es|it|nl|jp|kr|"
    r"ny|ca|tx|fl|wa|or|ma|il|nj|geo|state|city|local|region|"
    r"new[-_ ]york|los[-_ ]angeles|chicago|boston|miami|seattle|austin|dallas|denver)\b",
    re.IGNORECASE,
)
_BRAND_HINTS = re.compile(r"\bbrand|nonbrand|non[-_ ]brand|generic|competitor\b", re.IGNORECASE)
_TYPE_HINTS = re.compile(r"\bpmax|shopping|search|display|video|youtube|discovery|demand[-_ ]gen\b", re.IGNORECASE)


def _starving_campaigns(db: Database, account_id: str) -> list[tuple[str, str, float]]:
    anchor = anchor_date(db)
    return db.fetchall(
        windowed("""
        SELECT campaign_id, campaign_name, sum(conversions) as conv
        FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30 AND status = 'ENABLED'
        GROUP BY campaign_id, campaign_name
        HAVING sum(conversions) < 30 AND sum(conversions) > 0
        """, anchor),
        [account_id],
    )


def test_intentional_geo_split(db: Database, account_id: str) -> TestResult:
    rows = _starving_campaigns(db, account_id)
    if not rows:
        return TestResult("T1", "Intentional geo segmentation", "inconclusive",
                          "No starving campaigns visible.")
    geo_n = sum(1 for _, name, _ in rows if name and _GEO_HINTS.search(name))
    pct = geo_n / len(rows)
    ev = [{"starving_total": len(rows), "geo_named": geo_n, "geo_pct": round(pct, 2)}]
    if pct >= 0.5:
        return TestResult("T1", "Intentional geo segmentation", "disconfirm",
                          f"{geo_n}/{len(rows)} starving campaigns are geo-named — segmentation likely intentional, not a structural flaw.",
                          ev)
    return TestResult("T1", "Intentional geo segmentation", "confirm",
                      f"Only {geo_n}/{len(rows)} starving campaigns have geo names — over-segmentation isn't a geo-strategy artifact.",
                      ev)


def test_intentional_type_or_brand_split(db: Database, account_id: str) -> TestResult:
    rows = _starving_campaigns(db, account_id)
    if not rows:
        return TestResult("T2", "Intentional type/brand split", "inconclusive",
                          "No starving campaigns visible.")
    type_or_brand = sum(
        1 for _, name, _ in rows
        if name and (_TYPE_HINTS.search(name) or _BRAND_HINTS.search(name))
    )
    pct = type_or_brand / len(rows)
    ev = [{"starving_total": len(rows), "type_or_brand_named": type_or_brand,
           "pct": round(pct, 2)}]
    if pct >= 0.6:
        return TestResult("T2", "Intentional type/brand split", "disconfirm",
                          f"{type_or_brand}/{len(rows)} starving campaigns indicate type/brand splits — likely intentional.",
                          ev)
    return TestResult("T2", "Intentional type/brand split", "confirm",
                      f"Type/brand split signal weak ({type_or_brand}/{len(rows)}).", ev)


def test_starving_campaigns_share_of_spend(db: Database, account_id: str) -> TestResult:
    """If starving campaigns are <10% of spend, they're tests/exploration, not core."""
    anchor = anchor_date(db)
    row = db.fetchone(
        windowed("""
        WITH camp AS (
          SELECT campaign_id, sum(cost_micros)/1000000.0 as cost, sum(conversions) as conv
          FROM daily_metrics
          WHERE account_id = ? AND date >= current_date - 30 AND status = 'ENABLED'
          GROUP BY campaign_id
        )
        SELECT
          sum(CASE WHEN conv < 30 THEN cost ELSE 0 END) as starving_cost,
          sum(cost) as total_cost
        FROM camp
        """, anchor),
        [account_id],
    )
    s_cost, t_cost = (row or (0, 0))
    s_cost, t_cost = (s_cost or 0, t_cost or 0)
    if not t_cost:
        return TestResult("T3", "Starving share of spend", "inconclusive",
                          "No spend in 30d.")
    share = s_cost / t_cost
    ev = [{"starving_spend": round(s_cost, 2), "total_spend": round(t_cost, 2),
           "share": round(share, 3)}]
    if share < 0.10:
        return TestResult("T3", "Starving share of spend", "disconfirm",
                          f"Starving campaigns are only {share:.0%} of spend — likely test/exploration, not over-segmentation problem.",
                          ev)
    if share >= 0.30:
        return TestResult("T3", "Starving share of spend", "confirm",
                          f"Starving campaigns hold {share:.0%} of spend — meaningful share, consolidation matters.",
                          ev)
    return TestResult("T3", "Starving share of spend", "inconclusive",
                      f"Starving share {share:.0%} — moderate.", ev)


def audit_over_segmentation_signals(db: Database, limit: int | None = 50) -> list[SignalAudit]:
    sql = """
        SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''),
               s.message, s.data_json
        FROM signals s
        LEFT JOIN accounts a ON a.account_id = s.account_id
        WHERE s.signal_type = 'over_segmentation'
        ORDER BY s.detected_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = db.fetchall(sql)

    audits = []
    for sig_id, acct_id, acct_name, msg, data_json in rows:
        data = json.loads(data_json) if data_json else {}
        results = [
            test_intentional_geo_split(db, acct_id),
            test_intentional_type_or_brand_split(db, acct_id),
            test_starving_campaigns_share_of_spend(db, acct_id),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            detector_message=msg, detector_data=data,
            test_results=results,
        ))
    return audits
