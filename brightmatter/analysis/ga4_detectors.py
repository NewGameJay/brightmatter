"""GA4 detectors — Domains 1 & 2 (research/ga4/patterns/ga4-detection-logic.md).

Buildable now from ga4_landing_pages (landing_page x device x date engagement). All
CONFIRMED tier — GA4 directly measures engagement/bounce. The "what we can't tell
you" is always WHY (the cause) — that's the squirrelscan / firecrawl page-audit layer.

  1.1 engagement_rate_drop      — page engagement dropped >15pp vs baseline
  1.3 session_duration_collapse — page avg session duration dropped >50% vs baseline
  2.1 mobile_engagement_gap     — mobile engagement < desktop − 25pp on same page
  2.2 mobile_bounce_regression  — mobile bounce up >15pp while desktop stable

Domains needing un-ingested data are deferred: 1.2 paid-bounce + Domain 5 (need
source split / Tier 2.2), Domain 3 (needs funnel events / Tier 2.1), Domain 4
(page speed → squirrelscan, separate). Thresholds cite the research; a
config/ga4_thresholds.yaml is a follow-up once these are tuned against real volume.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from brightmatter.models.patterns import PatternDomain, Severity, Signal
from brightmatter.storage.database import Database

# thresholds (research/ga4/patterns + benchmarks)
ENG_DROP_PP = 0.15            # >15pp engagement drop = warning (Detector 1.1)
ENG_DROP_CRIT_PP = 0.25      # >25pp = critical
DURATION_DROP = 0.50         # >50% duration drop (Detector 1.3)
MOBILE_GAP_PP = 0.25         # mobile < desktop − 25pp (Detector 2.1; structural gap is ~12pp)
MOBILE_BOUNCE_PP = 0.15      # mobile bounce up >15pp while desktop stable (Detector 2.2)
DESKTOP_STABLE_PP = 0.05     # "desktop stable" tolerance
MIN_SESS_PAGE = 200          # ~50/week x 4 weeks (28d window)
MIN_SESS_DEVICE = 100        # per-device floor for the gap detector
RECENT_DAYS = 7
BASELINE_DAYS = 21           # the 21 days before the recent window


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _anchor(db: Database):
    return db.fetchone("SELECT max(date) FROM ga4_landing_pages")[0]


def _sig(account_id, page, stype, sev, value, threshold, msg, data) -> Signal:
    return Signal(
        signal_id=_id(), account_id=account_id, campaign_id="",
        domain=PatternDomain.LANDING_PAGE, signal_type=stype, severity=sev,
        value=float(value), threshold=float(threshold), message=msg,
        data={"landing_page": page, **data},
        detected_at=_now(),
        confidence_tier="CONFIRMED",
        what_we_know="GA4 directly measures session engagement on this landing page.",
        what_we_cant_rule_out="WHY engagement changed — page redesign, speed, broken element, "
                              "pop-up, content/message shift. Needs a page audit (squirrelscan).",
        check_next="Run squirrelscan on the page URL; check for a recent deploy/CMS change.",
    )


# ── Domain 1.1 / 1.3: engagement drop + duration collapse (page-level, time baseline) ──

def detect_engagement_drops(db: Database) -> list[Signal]:
    anchor = _anchor(db)
    if anchor is None:
        return []
    rows = db.fetchall(f"""
        WITH win AS (
            SELECT account_id, landing_page,
                   CASE WHEN date > DATE '{anchor}' - {RECENT_DAYS} THEN 'recent' ELSE 'base' END AS w,
                   sum(sessions) s, sum(engaged_sessions) es,
                   sum(avg_session_duration*sessions) durw
            FROM ga4_landing_pages
            WHERE date > DATE '{anchor}' - {RECENT_DAYS + BASELINE_DAYS}
              AND landing_page NOT IN ('(not set)','')
            GROUP BY 1,2,3
        ),
        p AS (
            SELECT account_id, landing_page,
                   sum(CASE WHEN w='recent' THEN s END) rs,
                   sum(CASE WHEN w='base' THEN s END) bs,
                   sum(CASE WHEN w='recent' THEN es END)*1.0/NULLIF(sum(CASE WHEN w='recent' THEN s END),0) r_eng,
                   sum(CASE WHEN w='base' THEN es END)*1.0/NULLIF(sum(CASE WHEN w='base' THEN s END),0) b_eng,
                   sum(CASE WHEN w='recent' THEN durw END)/NULLIF(sum(CASE WHEN w='recent' THEN s END),0) r_dur,
                   sum(CASE WHEN w='base' THEN durw END)/NULLIF(sum(CASE WHEN w='base' THEN s END),0) b_dur
            FROM win GROUP BY 1,2
        )
        SELECT account_id, landing_page, rs, bs, r_eng, b_eng, r_dur, b_dur
        FROM p WHERE rs >= {MIN_SESS_PAGE//4} AND bs >= {MIN_SESS_PAGE//2}
    """)
    out = []
    for acct, page, rs, bs, r_eng, b_eng, r_dur, b_dur in rows:
        if b_eng and r_eng is not None:
            drop = b_eng - r_eng
            if drop >= ENG_DROP_PP:
                sev = Severity.CRITICAL if drop >= ENG_DROP_CRIT_PP else Severity.WARNING
                out.append(_sig(acct, page, "ga4_engagement_drop", sev, r_eng, b_eng - ENG_DROP_PP,
                    f"Landing page {page} engagement fell {drop*100:.0f}pp "
                    f"({b_eng*100:.0f}%→{r_eng*100:.0f}%) over the last {RECENT_DAYS}d.",
                    {"recent_engagement": round(r_eng,3), "baseline_engagement": round(b_eng,3),
                     "recent_sessions": int(rs)}))
        if b_dur and r_dur is not None and b_dur > 0:
            ddrop = (b_dur - r_dur) / b_dur
            if ddrop >= DURATION_DROP:
                sev = Severity.WARNING if ddrop >= 0.75 else Severity.INFO
                out.append(_sig(acct, page, "ga4_session_duration_collapse", sev, r_dur, b_dur*(1-DURATION_DROP),
                    f"Landing page {page} avg session duration fell {ddrop*100:.0f}% "
                    f"({b_dur:.0f}s→{r_dur:.0f}s) over the last {RECENT_DAYS}d.",
                    {"recent_duration_s": round(r_dur,1), "baseline_duration_s": round(b_dur,1)}))
    return out


# ── Domain 2.1 / 2.2: mobile gap + mobile bounce regression ──

def detect_mobile_issues(db: Database) -> list[Signal]:
    anchor = _anchor(db)
    if anchor is None:
        return []
    # 2.1 cross-sectional mobile-vs-desktop engagement gap over the full window
    gap_rows = db.fetchall(f"""
        WITH d AS (
            SELECT account_id, landing_page, device, sum(sessions) s,
                   sum(engaged_sessions)*1.0/NULLIF(sum(sessions),0) eng
            FROM ga4_landing_pages WHERE landing_page NOT IN ('(not set)','') GROUP BY 1,2,3
        )
        SELECT m.account_id, m.landing_page, m.s, m.eng, dk.eng
        FROM d m JOIN d dk USING (account_id, landing_page)
        WHERE m.device='mobile' AND dk.device='desktop'
          AND m.s >= {MIN_SESS_DEVICE} AND dk.s >= {MIN_SESS_DEVICE}
          AND dk.eng - m.eng >= {MOBILE_GAP_PP}
    """)
    out = []
    for acct, page, ms, m_eng, d_eng in gap_rows:
        out.append(_sig(acct, page, "ga4_mobile_engagement_gap", Severity.WARNING, m_eng, d_eng - MOBILE_GAP_PP,
            f"Landing page {page}: mobile engagement {m_eng*100:.0f}% vs desktop {d_eng*100:.0f}% "
            f"(gap {(d_eng-m_eng)*100:.0f}pp, {int(ms)} mobile sessions) — mobile experience likely broken.",
            {"mobile_engagement": round(m_eng,3), "desktop_engagement": round(d_eng,3),
             "mobile_sessions": int(ms)}))

    # 2.2 mobile bounce regression with desktop as control
    reg_rows = db.fetchall(f"""
        WITH win AS (
            SELECT account_id, landing_page, device,
                   CASE WHEN date > DATE '{anchor}' - {RECENT_DAYS} THEN 'recent' ELSE 'base' END AS w,
                   sum(sessions) s, sum(sessions) - sum(engaged_sessions) bounced
            FROM ga4_landing_pages
            WHERE date > DATE '{anchor}' - {RECENT_DAYS + BASELINE_DAYS}
              AND landing_page NOT IN ('(not set)','')
            GROUP BY 1,2,3,4
        ),
        p AS (
            SELECT account_id, landing_page, device,
                   sum(CASE WHEN w='recent' THEN bounced END)*1.0/NULLIF(sum(CASE WHEN w='recent' THEN s END),0) r_b,
                   sum(CASE WHEN w='base' THEN bounced END)*1.0/NULLIF(sum(CASE WHEN w='base' THEN s END),0) b_b,
                   sum(CASE WHEN w='recent' THEN s END) rs
            FROM win GROUP BY 1,2,3
        )
        SELECT mo.account_id, mo.landing_page, mo.r_b, mo.b_b, dk.r_b, dk.b_b, mo.rs
        FROM p mo JOIN p dk USING (account_id, landing_page)
        WHERE mo.device='mobile' AND dk.device='desktop'
          AND mo.r_b IS NOT NULL AND mo.b_b IS NOT NULL AND dk.r_b IS NOT NULL AND dk.b_b IS NOT NULL
          AND mo.rs >= {MIN_SESS_DEVICE//2}
          AND (mo.r_b - mo.b_b) >= {MOBILE_BOUNCE_PP}
          AND abs(dk.r_b - dk.b_b) <= {DESKTOP_STABLE_PP}
    """)
    for acct, page, mr, mb, dr, dbase, rs in reg_rows:
        out.append(_sig(acct, page, "ga4_mobile_bounce_regression", Severity.WARNING, mr, mb + MOBILE_BOUNCE_PP,
            f"Landing page {page}: mobile bounce rose {(mr-mb)*100:.0f}pp "
            f"({mb*100:.0f}%→{mr*100:.0f}%) while desktop held — something broke on mobile.",
            {"mobile_bounce_recent": round(mr,3), "mobile_bounce_baseline": round(mb,3),
             "desktop_bounce_recent": round(dr,3)}))
    return out


# ── Domain 5.1: paid-vs-organic engagement gap (account level) ──

PAID_ORGANIC_GAP_PP = 0.20   # paid engagement >20pp below organic = targeting/message mismatch
MIN_CHANNEL_SESS = 200

def detect_traffic_source_gaps(db: Database) -> list[Signal]:
    rows = db.fetchall(f"""
        WITH paid AS (
            SELECT account_id, sessions, engagement_rate FROM ga4_source_engagement
            WHERE channel='Paid Search' AND sessions >= {MIN_CHANNEL_SESS}
        ),
        org AS (
            SELECT account_id, sessions, engagement_rate FROM ga4_source_engagement
            WHERE channel='Organic Search' AND sessions >= {MIN_CHANNEL_SESS}
        )
        SELECT p.account_id, p.engagement_rate, o.engagement_rate, p.sessions
        FROM paid p JOIN org o USING (account_id)
        WHERE o.engagement_rate - p.engagement_rate >= {PAID_ORGANIC_GAP_PP}
    """)
    out = []
    for acct, paid_eng, org_eng, ps in rows:
        out.append(Signal(
            signal_id=_id(), account_id=acct, campaign_id="",
            domain=PatternDomain.LANDING_PAGE, signal_type="ga4_paid_organic_gap",
            severity=Severity.INFO, value=float(paid_eng), threshold=float(org_eng - PAID_ORGANIC_GAP_PP),
            message=f"Paid-search engagement {paid_eng*100:.0f}% vs organic {org_eng*100:.0f}% "
                    f"(gap {(org_eng-paid_eng)*100:.0f}pp) — paid traffic engages worse than organic.",
            data={"paid_engagement": round(paid_eng,3), "organic_engagement": round(org_eng,3)},
            detected_at=_now(), confidence_tier="LIKELY",
            what_we_know="GA4 directly measures channel-segmented engagement.",
            what_we_cant_rule_out="Whether the paid TARGETING is too broad or the landing pages "
                                  "served to paid don't match the ad — some gap is expected (paid reaches wider).",
            check_next="Compare paid landing pages vs organic entry pages; check broad-match expansion.",
        ))
    return out


# ── Domain 3: ecommerce funnel step drop-off ──

FUNNEL_STEP_DROP = 0.20      # a step's conversion rate fell >20% recent vs baseline
FUNNEL_STEPS = [("view_item", "add_to_cart"), ("add_to_cart", "begin_checkout"),
                ("begin_checkout", "purchase")]
MIN_STEP_EVENTS = 50

def detect_funnel_dropoff(db: Database) -> list[Signal]:
    anchor = db.fetchone("SELECT max(date) FROM ga4_funnel_events")[0]
    if anchor is None:
        return []
    rows = db.fetchall(f"""
        SELECT account_id, event_name,
               sum(CASE WHEN date > DATE '{anchor}' - {RECENT_DAYS} THEN event_count END) recent,
               sum(CASE WHEN date <= DATE '{anchor}' - {RECENT_DAYS} THEN event_count END) base
        FROM ga4_funnel_events
        WHERE date > DATE '{anchor}' - {RECENT_DAYS + 21}
        GROUP BY 1,2
    """)
    byacct = {}
    for acct, ev, recent, base in rows:
        byacct.setdefault(acct, {})[ev] = (recent or 0, base or 0)
    out = []
    for acct, ev in byacct.items():
        def rate(top, bot, w):  # w: 0=recent, 1=base
            t = ev.get(top, (0, 0))[w]; b = ev.get(bot, (0, 0))[w]
            return (t / b) if b else None
        step_changes = {}
        for upstream, downstream in FUNNEL_STEPS:
            r = rate(downstream, upstream, 0); b = rate(downstream, upstream, 1)
            # volume floor on the upstream step (baseline)
            if b and r is not None and ev.get(upstream, (0, 0))[1] >= MIN_STEP_EVENTS:
                step_changes[(upstream, downstream)] = (r, b, (b - r) / b if b else 0)
        if not step_changes:
            continue
        # Detector 3.1: one step dropped >20% — flag the worst
        worst = max(step_changes.items(), key=lambda kv: kv[1][2])
        (up, down), (r, b, drop) = worst
        if drop >= FUNNEL_STEP_DROP:
            # is it isolated (other steps stable)?
            others = [v[2] for k, v in step_changes.items() if k != (up, down)]
            isolated = all(o < FUNNEL_STEP_DROP for o in others) if others else True
            out.append(Signal(
                signal_id=_id(), account_id=acct, campaign_id="",
                domain=PatternDomain.LANDING_PAGE, signal_type="ga4_funnel_dropoff",
                severity=Severity.CRITICAL if down == "purchase" else Severity.WARNING,
                value=float(r), threshold=float(b * (1 - FUNNEL_STEP_DROP)),
                message=f"Funnel step {up}->{down} conversion fell {drop*100:.0f}% "
                        f"({b*100:.0f}%->{r*100:.0f}%)" + (" (isolated step)" if isolated else " (broad)") + ".",
                data={"step": f"{up}->{down}", "recent_rate": round(r,3), "baseline_rate": round(b,3),
                      "isolated": isolated},
                detected_at=_now(), confidence_tier="CONFIRMED" if isolated else "LIKELY",
                what_we_know="GA4 event counts directly measure funnel step conversion.",
                what_we_cant_rule_out="What broke the step — product/pricing (cart), checkout friction "
                                      "(payment/shipping), or a tracking change.",
                check_next="Inspect that funnel step on the site; check for a deploy/price/checkout change.",
            ))
    return out


def run_ga4_detectors(db: Database) -> list[Signal]:
    sigs = (detect_engagement_drops(db) + detect_mobile_issues(db)
            + detect_traffic_source_gaps(db) + detect_funnel_dropoff(db))
    return sigs
