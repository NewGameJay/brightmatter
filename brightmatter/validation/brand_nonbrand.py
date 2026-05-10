"""Disconfirmation harness for `detect_brand_nonbrand_contamination`.

The detector claims: an account's blended ROAS is masking poor non-brand
performance, identified by `campaign_name LIKE '%brand%'` plus a ROAS gap.

This harness runs independent tests on adjacent data — keyword text, match
types, conversion volume, change history — and labels each signal's claim
as `confirm`, `disconfirm`, or `inconclusive` per test.
"""

from __future__ import annotations

import json
import re

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult, Verdict

# Generic stopwords stripped from account names when extracting brand tokens.
# Anything left over is a candidate brand identifier.
_STOPWORDS = {
    "inc", "llc", "ltd", "corp", "co", "company", "the", "and", "of", "for",
    "google", "ads", "ad", "account", "active", "paid", "grant", "us", "uk",
    "ca", "eu", "au", "usa", "agency", "agency.", "media", "client", "master",
    "strat", "main", "new", "old", "test", "demo", "store", "shop", "online",
    "marketing", "digital", "brand", "branded", "nonbrand", "non",
}


# ── Helpers (also imported by the detector for pre-fire guards) ──

def brand_tokens_for_account(account_name: str) -> list[str]:
    """Public wrapper around the brand-token tokenizer."""
    return _brand_tokens(account_name)


def _brand_tokens(account_name: str) -> list[str]:
    """Extract candidate brand tokens from an account name."""
    if not account_name:
        return []
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", account_name.lower())
    tokens = [t for t in cleaned.split() if len(t) >= 3 and t not in _STOPWORDS]
    # Deduplicate while preserving order
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _ilike_any(column: str, n: int) -> str:
    """Build a SQL clause like (col ILIKE ? OR col ILIKE ? ...) for n params."""
    return "(" + " OR ".join([f"{column} ILIKE ?" for _ in range(n)]) + ")"


def brand_token_pct_per_campaign(
    db: Database, account_id: str, brand_tokens: list[str], window_days: int = 30
) -> dict[str, float]:
    """Return {campaign_name: pct_brand_token_keywords} for the account.

    Used by both the post-hoc harness and the pre-fire detector guard so the
    naming-heuristic check has a single source of truth.
    """
    if not brand_tokens:
        return {}
    n = len(brand_tokens)
    params = [account_id] + [f"%{t}%" for t in brand_tokens] + [account_id, window_days]
    rows = db.fetchall(
        f"""
        WITH camp_labels AS (
            SELECT DISTINCT campaign_id, campaign_name
            FROM daily_metrics
            WHERE account_id = ? AND date >= current_date - 30
        ),
        kw AS (
            SELECT campaign_id,
                   COUNT(DISTINCT keyword_id) as kw_total,
                   COUNT(DISTINCT CASE WHEN {_ilike_any('keyword_text', n)}
                                        THEN keyword_id END) as kw_brand_match
            FROM keyword_metrics
            WHERE account_id = ? AND week_start >= current_date - ?
            GROUP BY campaign_id
        )
        SELECT cl.campaign_name,
               COALESCE(kw.kw_total, 0) as kw_total,
               COALESCE(kw.kw_brand_match, 0) as kw_brand_match
        FROM camp_labels cl
        LEFT JOIN kw USING (campaign_id)
        WHERE COALESCE(kw.kw_total, 0) >= 3
        """,
        params,
    )
    return {
        name: (matched / total) if total else 0.0
        for name, total, matched in rows
    }


# ── Tests ──

def test_naming_heuristic(
    db: Database, account_id: str, brand_tokens: list[str]
) -> TestResult:
    """T1 — Are 'brand'-labeled campaigns actually brand-keyword dominant?

    Disconfirms if a campaign matched by name has <30% brand-token coverage
    in its active keywords, or if a 'non-brand' campaign has >30%.
    """
    if not brand_tokens:
        return TestResult(
            "T1", "Naming heuristic vs keyword reality",
            "inconclusive",
            "No brand tokens extractable from account name; cannot validate naming.",
        )

    n = len(brand_tokens)
    params = [account_id] + [f"%{t}%" for t in brand_tokens]
    rows = db.fetchall(
        f"""
        WITH camp_labels AS (
            SELECT DISTINCT campaign_id, campaign_name,
                   CASE WHEN lower(campaign_name) LIKE '%brand%' THEN 'brand' ELSE 'nonbrand' END as label
            FROM daily_metrics
            WHERE account_id = ? AND date >= current_date - 30
        ),
        kw AS (
            SELECT campaign_id,
                   COUNT(DISTINCT keyword_id) as kw_total,
                   COUNT(DISTINCT CASE WHEN {_ilike_any('keyword_text', n)}
                                        THEN keyword_id END) as kw_brand_match
            FROM keyword_metrics
            WHERE account_id = ?
              AND week_start >= current_date - 60
            GROUP BY campaign_id
        )
        SELECT cl.campaign_name, cl.label,
               COALESCE(kw.kw_total, 0) as kw_total,
               COALESCE(kw.kw_brand_match, 0) as kw_brand_match
        FROM camp_labels cl
        LEFT JOIN kw USING (campaign_id)
        WHERE COALESCE(kw.kw_total, 0) >= 3
        ORDER BY kw_total DESC
        """,
        params + [account_id],
    )

    if not rows:
        return TestResult(
            "T1", "Naming heuristic vs keyword reality",
            "inconclusive",
            "No campaigns with >=3 keywords ingested; cannot validate naming.",
        )

    evidence = []
    disconfirms = []
    confirms = []
    for campaign_name, label, kw_total, kw_brand_match in rows:
        pct = (kw_brand_match / kw_total) if kw_total else 0
        evidence.append({
            "campaign": campaign_name, "label": label,
            "keyword_count": kw_total, "brand_token_matches": kw_brand_match,
            "brand_token_pct": round(pct, 3),
        })
        if label == "brand" and pct < 0.30:
            disconfirms.append(f"'{campaign_name}' labeled brand but only {pct:.0%} brand-token kws")
        elif label == "nonbrand" and pct > 0.30:
            disconfirms.append(f"'{campaign_name}' labeled non-brand but {pct:.0%} brand-token kws")
        elif label == "brand" and pct >= 0.50:
            confirms.append(f"'{campaign_name}' is genuinely brand-dominant ({pct:.0%})")
        elif label == "nonbrand" and pct <= 0.15:
            confirms.append(f"'{campaign_name}' is genuinely non-brand ({pct:.0%})")

    if disconfirms:
        return TestResult(
            "T1", "Naming heuristic vs keyword reality", "disconfirm",
            "Mismatch between campaign label and keyword composition: " + "; ".join(disconfirms[:3]),
            evidence,
        )
    if confirms:
        return TestResult(
            "T1", "Naming heuristic vs keyword reality", "confirm",
            "Campaign labels match keyword composition: " + "; ".join(confirms[:3]),
            evidence,
        )
    return TestResult(
        "T1", "Naming heuristic vs keyword reality", "inconclusive",
        "Keyword composition is ambiguous (mid-range brand-token coverage).",
        evidence,
    )


def test_match_type_structure(db: Database, account_id: str) -> TestResult:
    """T2 — Is the brand vs non-brand structure consistent with Alpha-Beta intent?

    Geddes/Lolk: brand campaigns should be 70%+ exact/phrase (protection),
    non-brand can be broader (discovery). Inverted structure suggests labels
    don't reflect actual intent.
    """
    rows = db.fetchall(
        """
        WITH camp_labels AS (
            SELECT DISTINCT account_id, campaign_id, campaign_name,
                   CASE WHEN lower(campaign_name) LIKE '%brand%' THEN 'brand' ELSE 'nonbrand' END as label
            FROM daily_metrics
            WHERE account_id = ? AND date >= current_date - 30
        )
        SELECT cl.label, cl.campaign_name,
               kc.exact_count, kc.phrase_count, kc.broad_count, kc.keyword_count
        FROM camp_labels cl
        JOIN keyword_counts kc USING (account_id, campaign_id)
        WHERE kc.keyword_count >= 3
        """,
        [account_id],
    )

    if not rows:
        return TestResult(
            "T2", "Match-type structure (Alpha-Beta sanity)",
            "inconclusive",
            "No keyword_counts data for campaigns in this account.",
        )

    evidence = []
    disconfirms = []
    confirms = []
    for label, name, exact, phrase, broad, total in rows:
        ep_pct = ((exact or 0) + (phrase or 0)) / total if total else 0
        broad_pct = (broad or 0) / total if total else 0
        evidence.append({
            "campaign": name, "label": label,
            "exact": exact, "phrase": phrase, "broad": broad, "total": total,
            "exact_phrase_pct": round(ep_pct, 3),
            "broad_pct": round(broad_pct, 3),
        })
        if label == "brand" and broad_pct > 0.50:
            disconfirms.append(f"'{name}' brand campaign is {broad_pct:.0%} broad (not Alpha-Beta protection)")
        elif label == "nonbrand" and ep_pct > 0.70:
            disconfirms.append(f"'{name}' non-brand campaign is {ep_pct:.0%} exact/phrase (looks like a brand-protection structure)")
        elif label == "brand" and ep_pct >= 0.70:
            confirms.append(f"'{name}' brand campaign is {ep_pct:.0%} exact/phrase (proper protection)")

    if disconfirms:
        return TestResult(
            "T2", "Match-type structure (Alpha-Beta sanity)", "disconfirm",
            "; ".join(disconfirms[:3]),
            evidence,
        )
    if confirms:
        return TestResult(
            "T2", "Match-type structure (Alpha-Beta sanity)", "confirm",
            "; ".join(confirms[:3]),
            evidence,
        )
    return TestResult(
        "T2", "Match-type structure (Alpha-Beta sanity)", "inconclusive",
        "Match-type mix is mid-range; no clear structural signal.",
        evidence,
    )


def test_volume_reliability(db: Database, account_id: str) -> TestResult:
    """T3 — Is non-brand conversion volume large enough for the ROAS claim to be real?

    With <10 non-brand conversions, the 'low ROAS' could be statistical noise.
    """
    row = db.fetchone(
        """
        SELECT
            sum(CASE WHEN lower(campaign_name) LIKE '%brand%' THEN conversions ELSE 0 END) as brand_convs,
            sum(CASE WHEN lower(campaign_name) NOT LIKE '%brand%' THEN conversions ELSE 0 END) as nonbrand_convs,
            sum(CASE WHEN lower(campaign_name) LIKE '%brand%' THEN clicks ELSE 0 END) as brand_clicks,
            sum(CASE WHEN lower(campaign_name) NOT LIKE '%brand%' THEN clicks ELSE 0 END) as nonbrand_clicks
        FROM daily_metrics
        WHERE account_id = ? AND date >= current_date - 30
        """,
        [account_id],
    )
    brand_c, nb_c, brand_cl, nb_cl = (row or (0, 0, 0, 0))
    brand_c, nb_c = (brand_c or 0), (nb_c or 0)

    evidence = [{
        "brand_conversions_30d": brand_c, "nonbrand_conversions_30d": nb_c,
        "brand_clicks_30d": brand_cl, "nonbrand_clicks_30d": nb_cl,
    }]
    if nb_c < 10:
        return TestResult(
            "T3", "Volume reliability (non-brand conv count)", "disconfirm",
            f"Only {nb_c:.0f} non-brand conversions in 30d — ROAS estimate is statistical noise.",
            evidence,
        )
    if nb_c >= 30 and brand_c >= 30:
        return TestResult(
            "T3", "Volume reliability (non-brand conv count)", "confirm",
            f"Both sides have sufficient volume (brand={brand_c:.0f}, nonbrand={nb_c:.0f} convs in 30d).",
            evidence,
        )
    return TestResult(
        "T3", "Volume reliability (non-brand conv count)", "inconclusive",
        f"Mid-range volume (brand={brand_c:.0f}, nonbrand={nb_c:.0f}); ROAS suggestive but not definitive.",
        evidence,
    )


def test_tracking_integrity(db: Database, account_id: str) -> TestResult:
    """T4 — Did conversion tracking change recently? (Vallaeys C7)"""
    rows = db.fetchall(
        """
        SELECT change_timestamp, change_type, resource_type, actor
        FROM change_events
        WHERE account_id = ?
          AND change_timestamp >= current_date - 60
          AND (
              upper(resource_type) LIKE '%CONVERSION%'
              OR upper(change_type) LIKE '%CONVERSION%'
          )
        ORDER BY change_timestamp DESC
        LIMIT 20
        """,
        [account_id],
    )
    evidence = [{
        "timestamp": str(r[0]), "change_type": r[1],
        "resource_type": r[2], "actor": r[3],
    } for r in rows]

    if rows:
        return TestResult(
            "T4", "Conversion tracking integrity", "disconfirm",
            f"{len(rows)} conversion-related change event(s) in last 60d — ROAS gap may be a tracking artifact, not contamination.",
            evidence,
        )
    return TestResult(
        "T4", "Conversion tracking integrity", "confirm",
        "No conversion-tracking changes in last 60d.",
        evidence,
    )


def test_brand_roas_plausibility(brand_roas: float) -> TestResult:
    """T5 — Is the brand ROAS suspiciously high?

    Brand ROAS > 25x in ecommerce typically indicates conversion value
    inflation (offline imports, LTV blending, double-counting) — meaning the
    'gap' is partly artifact.
    """
    evidence = [{"brand_roas": round(brand_roas, 2)}]
    if brand_roas > 25:
        return TestResult(
            "T5", "Brand ROAS plausibility", "disconfirm",
            f"Brand ROAS of {brand_roas:.1f}x is implausibly high — conversion value likely inflated, gap partly artifact.",
            evidence,
        )
    if brand_roas <= 15:
        return TestResult(
            "T5", "Brand ROAS plausibility", "confirm",
            f"Brand ROAS of {brand_roas:.1f}x is in plausible range.",
            evidence,
        )
    return TestResult(
        "T5", "Brand ROAS plausibility", "inconclusive",
        f"Brand ROAS of {brand_roas:.1f}x is high but not extreme; could be legitimate or partly inflated.",
        evidence,
    )


# ── Orchestration ──

def audit_brand_nonbrand_signals(db: Database) -> list[SignalAudit]:
    """Run the harness against every roas_contamination signal in storage."""
    signal_rows = db.fetchall(
        """
        SELECT s.signal_id, s.account_id, s.message, s.data_json,
               COALESCE(a.account_name, ''), COALESCE(a.business_type, 'unknown')
        FROM signals s
        LEFT JOIN accounts a USING (account_id)
        WHERE s.signal_type = 'roas_contamination'
        ORDER BY s.detected_at DESC
        """
    )

    audits: list[SignalAudit] = []
    for sig_id, acct_id, msg, data_json, acct_name, biz_type in signal_rows:
        data = json.loads(data_json) if data_json else {}
        tokens = _brand_tokens(acct_name)
        results = [
            test_naming_heuristic(db, acct_id, tokens),
            test_match_type_structure(db, acct_id),
            test_volume_reliability(db, acct_id),
            test_tracking_integrity(db, acct_id),
            test_brand_roas_plausibility(data.get("brand_roas", 0.0)),
        ]
        audits.append(SignalAudit(
            signal_id=sig_id, account_id=acct_id, account_name=acct_name,
            business_type=biz_type, detector_message=msg,
            detector_data=data, brand_tokens_used=tokens,
            test_results=results,
        ))
    return audits
