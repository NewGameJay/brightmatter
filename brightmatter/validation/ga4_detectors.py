"""Disconfirmation harnesses for the 4 GA4 detectors.

Same rigor as the Google Ads harnesses — and arguably more important: a false-positive
GA4 signal upgrades a Google Ads signal to CONFIRMED (ga4_crossref), so a bad GA4
signal is worse than an Ads signal staying at LIKELY. Each harness recomputes from
ga4_landing_pages and challenges the fired signal.

Tests look for the usual GA4 artifacts: thin volume (noise), site-wide drops (tracking/
seasonal, not page-specific), benign reversion from an unusually high baseline, and
traffic-mix shifts (duration collapses when a campaign floods a page with shallow
visits, not because the page degraded).
"""

from __future__ import annotations

import json

from brightmatter.storage.database import Database
from brightmatter.validation._base import SignalAudit, TestResult

RECENT = 7
BASE = 21
MIN_RECENT_SESS = 50          # research floor: 50 sessions/week
BENCHMARK_ENG = 0.526         # cross-industry median engagement
MOBILE_STRUCTURAL_PP = 0.12   # structural mobile-desktop gap


def _anchor(db: Database):
    return db.fetchone("SELECT max(date) FROM ga4_landing_pages")[0]


def _page_windows(db: Database, account_id: str, page: str, anchor):
    """(recent_sess, recent_eng, base_sess, base_eng) for a page, devices aggregated."""
    r = db.fetchone(f"""
        SELECT
          sum(CASE WHEN date > DATE '{anchor}' - {RECENT} THEN sessions END) rs,
          sum(CASE WHEN date > DATE '{anchor}' - {RECENT} THEN engaged_sessions END)*1.0
            /NULLIF(sum(CASE WHEN date > DATE '{anchor}' - {RECENT} THEN sessions END),0) re,
          sum(CASE WHEN date <= DATE '{anchor}' - {RECENT} THEN sessions END) bs,
          sum(CASE WHEN date <= DATE '{anchor}' - {RECENT} THEN engaged_sessions END)*1.0
            /NULLIF(sum(CASE WHEN date <= DATE '{anchor}' - {RECENT} THEN sessions END),0) be
        FROM ga4_landing_pages
        WHERE account_id=? AND landing_page=? AND date > DATE '{anchor}' - {RECENT + BASE}
    """, [account_id, page])
    return r or (None, None, None, None)


def _account_engagement_shift(db: Database, account_id: str, anchor, exclude_page: str):
    """Median per-page engagement shift (recent−base) across the account's OTHER pages —
    the site-wide control. If the whole property dropped, the page isn't special."""
    rows = db.fetchall(f"""
        WITH p AS (
          SELECT landing_page,
            sum(CASE WHEN date > DATE '{anchor}' - {RECENT} THEN engaged_sessions END)*1.0
              /NULLIF(sum(CASE WHEN date > DATE '{anchor}' - {RECENT} THEN sessions END),0) re,
            sum(CASE WHEN date <= DATE '{anchor}' - {RECENT} THEN engaged_sessions END)*1.0
              /NULLIF(sum(CASE WHEN date <= DATE '{anchor}' - {RECENT} THEN sessions END),0) be,
            sum(sessions) s
          FROM ga4_landing_pages
          WHERE account_id=? AND landing_page NOT IN ('(not set)','(other)','')
            AND landing_page <> ? AND date > DATE '{anchor}' - {RECENT + BASE}
          GROUP BY 1 HAVING sum(sessions) >= {MIN_RECENT_SESS}
        )
        SELECT median(re - be) FROM p WHERE re IS NOT NULL AND be IS NOT NULL
    """, [account_id, exclude_page])
    return rows[0][0] if rows and rows[0][0] is not None else None


def _device(db: Database, account_id: str, page: str, anchor):
    """(mobile_sess, mobile_eng, desktop_sess, desktop_eng) full window."""
    r = db.fetchone("""
        SELECT
          sum(CASE WHEN device='mobile' THEN sessions END) ms,
          sum(CASE WHEN device='mobile' THEN engaged_sessions END)*1.0/NULLIF(sum(CASE WHEN device='mobile' THEN sessions END),0) me,
          sum(CASE WHEN device='desktop' THEN sessions END) ds,
          sum(CASE WHEN device='desktop' THEN engaged_sessions END)*1.0/NULLIF(sum(CASE WHEN device='desktop' THEN sessions END),0) de
        FROM ga4_landing_pages WHERE account_id=? AND landing_page=?
    """, [account_id, page])
    return r or (None, None, None, None)


def _load(db: Database, signal_type: str, limit: int | None = 100):
    sql = """SELECT s.signal_id, s.account_id, COALESCE(a.account_name,''), s.message, s.data_json
             FROM signals s LEFT JOIN accounts a ON a.account_id=s.account_id
             WHERE s.signal_type=? ORDER BY s.detected_at DESC"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.fetchall(sql, [signal_type])


def _page_of(data_json):
    try:
        return (json.loads(data_json) if data_json else {}).get("landing_page", "")
    except Exception:
        return ""


# ── engagement_drop ──
def audit_ga4_engagement_drop_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    anchor = _anchor(db)
    audits = []
    for sid, acct, name, msg, dj in _load(db, "ga4_engagement_drop", limit):
        page = _page_of(dj)
        rs, re, bs, be = _page_windows(db, acct, page, anchor)
        tests = []
        # T1 volume
        if not rs or rs < MIN_RECENT_SESS:
            tests.append(TestResult("T1", "Recent volume", "disconfirm",
                f"Only {rs or 0:.0f} recent sessions (<{MIN_RECENT_SESS}) — drop is likely noise.",
                [{"recent_sessions": rs}]))
        else:
            tests.append(TestResult("T1", "Recent volume", "confirm",
                f"{rs:.0f} recent sessions — enough to be reliable.", [{"recent_sessions": rs}]))
        # T2 site-wide vs isolated
        shift = _account_engagement_shift(db, acct, anchor, page)
        if shift is not None and shift <= -0.10:
            tests.append(TestResult("T2", "Page-isolated vs site-wide", "disconfirm",
                f"The account's other pages also fell (median {shift*100:.0f}pp) — site/tracking issue, not this page.",
                [{"account_median_shift": round(shift,3)}]))
        else:
            tests.append(TestResult("T2", "Page-isolated vs site-wide", "confirm",
                f"Other pages stable (median {((shift or 0)*100):.0f}pp) — the drop is specific to this page.",
                [{"account_median_shift": round(shift,3) if shift is not None else None}]))
        # T3 absolute level (benign reversion vs genuinely weak)
        if re is not None and re >= 0.55:
            tests.append(TestResult("T3", "Absolute engagement level", "disconfirm",
                f"Recent engagement still {re*100:.0f}% (above benchmark) — likely benign reversion from a high baseline.",
                [{"recent_engagement": round(re,3)}]))
        elif re is not None and re < BENCHMARK_ENG:
            tests.append(TestResult("T3", "Absolute engagement level", "confirm",
                f"Recent engagement {re*100:.0f}% is below the {BENCHMARK_ENG*100:.0f}% benchmark — genuinely weak.",
                [{"recent_engagement": round(re,3)}]))
        else:
            tests.append(TestResult("T3", "Absolute engagement level", "inconclusive",
                f"Recent engagement {(re or 0)*100:.0f}% — borderline.", [{"recent_engagement": re}]))
        audits.append(SignalAudit(sid, acct, name, msg, json.loads(dj) if dj else {}, tests))
    return audits


# ── session_duration_collapse ──
def audit_ga4_session_duration_collapse_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    anchor = _anchor(db)
    audits = []
    for sid, acct, name, msg, dj in _load(db, "ga4_session_duration_collapse", limit):
        page = _page_of(dj)
        rs, re, bs, be = _page_windows(db, acct, page, anchor)
        tests = []
        if not rs or rs < MIN_RECENT_SESS:
            tests.append(TestResult("T1", "Recent volume", "disconfirm",
                f"Only {rs or 0:.0f} recent sessions — duration is noisy.", [{"recent_sessions": rs}]))
        else:
            tests.append(TestResult("T1", "Recent volume", "confirm",
                f"{rs:.0f} recent sessions.", [{"recent_sessions": rs}]))
        # T2 traffic-mix: did sessions surge? duration drops when a campaign floods the page
        if rs and bs:
            # normalize to per-day (recent 7d vs base 21d)
            r_rate = rs / RECENT; b_rate = bs / BASE
            if b_rate > 0 and r_rate / b_rate >= 1.5:
                tests.append(TestResult("T2", "Traffic-mix shift", "disconfirm",
                    f"Recent sessions/day surged {r_rate/b_rate:.1f}x — duration drop reflects a traffic flood, not page decay.",
                    [{"recent_per_day": round(r_rate,1), "base_per_day": round(b_rate,1)}]))
            else:
                tests.append(TestResult("T2", "Traffic-mix shift", "confirm",
                    f"Traffic volume steady ({r_rate/b_rate:.1f}x) — the duration drop isn't a volume artifact.",
                    [{"ratio": round(r_rate/b_rate,2)}]))
        else:
            tests.append(TestResult("T2", "Traffic-mix shift", "inconclusive", "Insufficient volume to compare."))
        # T3 site-wide engagement control
        shift = _account_engagement_shift(db, acct, anchor, page)
        tests.append(TestResult("T3", "Page-isolated vs site-wide",
            "disconfirm" if (shift is not None and shift <= -0.10) else "confirm",
            f"Account median engagement shift {((shift or 0)*100):.0f}pp.", [{"shift": shift}]))
        audits.append(SignalAudit(sid, acct, name, msg, json.loads(dj) if dj else {}, tests))
    return audits


# ── mobile_engagement_gap ──
def audit_ga4_mobile_engagement_gap_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    anchor = _anchor(db)
    audits = []
    for sid, acct, name, msg, dj in _load(db, "ga4_mobile_engagement_gap", limit):
        page = _page_of(dj)
        ms, me, ds, de = _device(db, acct, page, anchor)
        tests = []
        # T1 volume per device
        if not ms or not ds or ms < 100 or ds < 100:
            tests.append(TestResult("T1", "Per-device volume", "disconfirm",
                f"Thin device volume (mobile {ms or 0:.0f}, desktop {ds or 0:.0f}).", [{"mobile": ms, "desktop": ds}]))
        else:
            tests.append(TestResult("T1", "Per-device volume", "confirm",
                f"mobile {ms:.0f} / desktop {ds:.0f} sessions.", [{"mobile": ms, "desktop": ds}]))
        # T2 beyond structural gap
        gap = (de - me) if (de is not None and me is not None) else 0
        if gap >= 0.30:
            tests.append(TestResult("T2", "Beyond structural gap", "confirm",
                f"Gap {gap*100:.0f}pp >> structural {MOBILE_STRUCTURAL_PP*100:.0f}pp — page-specific mobile problem.",
                [{"gap_pp": round(gap,3)}]))
        elif gap >= 0.25:
            tests.append(TestResult("T2", "Beyond structural gap", "inconclusive",
                f"Gap {gap*100:.0f}pp — above threshold but not dramatic.", [{"gap_pp": round(gap,3)}]))
        else:
            tests.append(TestResult("T2", "Beyond structural gap", "disconfirm",
                f"Gap {gap*100:.0f}pp near structural — may be normal device difference.", [{"gap_pp": round(gap,3)}]))
        # T3 mobile genuinely weak (not just desktop unusually high)
        if me is not None and me < 0.40:
            tests.append(TestResult("T3", "Mobile absolute level", "confirm",
                f"Mobile engagement {me*100:.0f}% is poor in absolute terms.", [{"mobile_engagement": round(me,3)}]))
        else:
            tests.append(TestResult("T3", "Mobile absolute level", "inconclusive",
                f"Mobile engagement {(me or 0)*100:.0f}% — gap may be desktop running hot.", [{"mobile_engagement": me}]))
        audits.append(SignalAudit(sid, acct, name, msg, json.loads(dj) if dj else {}, tests))
    return audits


# ── mobile_bounce_regression ──
def audit_ga4_mobile_bounce_regression_signals(db: Database, limit: int | None = 100) -> list[SignalAudit]:
    anchor = _anchor(db)
    audits = []
    for sid, acct, name, msg, dj in _load(db, "ga4_mobile_bounce_regression", limit):
        page = _page_of(dj)
        # recompute per-device recent vs base bounce
        r = db.fetchone(f"""
            SELECT
              sum(CASE WHEN device='mobile' AND date> DATE '{anchor}'-{RECENT} THEN sessions-engaged_sessions END)*1.0
                /NULLIF(sum(CASE WHEN device='mobile' AND date> DATE '{anchor}'-{RECENT} THEN sessions END),0) mr,
              sum(CASE WHEN device='mobile' AND date<=DATE '{anchor}'-{RECENT} THEN sessions-engaged_sessions END)*1.0
                /NULLIF(sum(CASE WHEN device='mobile' AND date<=DATE '{anchor}'-{RECENT} THEN sessions END),0) mb,
              sum(CASE WHEN device='desktop' AND date> DATE '{anchor}'-{RECENT} THEN sessions-engaged_sessions END)*1.0
                /NULLIF(sum(CASE WHEN device='desktop' AND date> DATE '{anchor}'-{RECENT} THEN sessions END),0) dr,
              sum(CASE WHEN device='desktop' AND date<=DATE '{anchor}'-{RECENT} THEN sessions-engaged_sessions END)*1.0
                /NULLIF(sum(CASE WHEN device='desktop' AND date<=DATE '{anchor}'-{RECENT} THEN sessions END),0) db_,
              sum(CASE WHEN device='mobile' AND date> DATE '{anchor}'-{RECENT} THEN sessions END) mrs
            FROM ga4_landing_pages WHERE account_id=? AND landing_page=? AND date> DATE '{anchor}'-{RECENT+BASE}
        """, [acct, page])
        mr, mb, dr, db_, mrs = r or (None,)*5
        tests = []
        tests.append(TestResult("T1", "Mobile recent volume",
            "confirm" if (mrs and mrs >= 50) else "disconfirm",
            f"{mrs or 0:.0f} recent mobile sessions.", [{"mobile_recent_sessions": mrs}]))
        # T2 desktop control validity
        if dr is not None and db_ is not None and abs(dr - db_) <= 0.05:
            tests.append(TestResult("T2", "Desktop control stable", "confirm",
                f"Desktop bounce held ({db_*100:.0f}%→{dr*100:.0f}%) — valid control.", [{"desktop_delta": round(dr-db_,3)}]))
        else:
            tests.append(TestResult("T2", "Desktop control stable", "disconfirm",
                f"Desktop also moved ({(dr or 0)*100:.0f} vs {(db_ or 0)*100:.0f}) — not mobile-specific.",
                [{"desktop_delta": (dr-db_) if (dr is not None and db_ is not None) else None}]))
        # T3 magnitude
        if mr is not None and mb is not None and (mr - mb) >= 0.15:
            tests.append(TestResult("T3", "Mobile bounce magnitude", "confirm",
                f"Mobile bounce rose {(mr-mb)*100:.0f}pp.", [{"mobile_bounce_delta": round(mr-mb,3)}]))
        else:
            tests.append(TestResult("T3", "Mobile bounce magnitude", "inconclusive",
                f"Mobile bounce delta {((mr or 0)-(mb or 0))*100:.0f}pp.", []))
        audits.append(SignalAudit(sid, acct, name, msg, json.loads(dj) if dj else {}, tests))
    return audits
