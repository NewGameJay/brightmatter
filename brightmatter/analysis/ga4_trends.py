"""GA4 #3 — engagement trend detection.

Distinguishes "this page is degrading" from "this page was always bad" — the question
the engagement_drop detector alone can't answer. Same OLS approach as Phase 2 for
Google Ads (scipy.linregress via analysis.trends.compute_trend), run on the daily
engagement series per landing page in ga4_landing_pages.

Engagement is higher-is-better, so we borrow the 'cvr' favorability (improving =
slope up & significant, declining = slope down & significant, else stable/volatile).
Persists ga4_page_trends and annotates engagement_drop signals with the trajectory.
"""

from __future__ import annotations

from brightmatter.analysis.trends import compute_trend
from brightmatter.storage.database import Database

MIN_DAYS = 10
MIN_SESSIONS = 200


def compute_engagement_trends(db: Database) -> dict:
    rows = db.fetchall("""
        SELECT account_id, landing_page, date,
               sum(sessions) s, sum(engaged_sessions) es
        FROM ga4_landing_pages
        WHERE landing_page NOT IN ('(not set)','(other)','')
        GROUP BY 1,2,3 ORDER BY 1,2,3
    """)
    series: dict[tuple, list] = {}
    for acct, page, d, s, es in rows:
        if not s:
            continue
        series.setdefault((acct, page), []).append((d, es / s, s))

    db.execute("DELETE FROM ga4_page_trends")
    dist = {"improving": 0, "declining": 0, "stable": 0, "volatile": 0}
    n = 0
    for (acct, page), pts in series.items():
        if len(pts) < MIN_DAYS:
            continue
        total_sess = sum(p[2] for p in pts)
        if total_sess < MIN_SESSIONS:
            continue
        dates = [p[0] for p in pts]
        vals = [p[1] for p in pts]
        t = compute_trend(dates, vals, "cvr", min_points=MIN_DAYS)
        if t is None:
            continue
        dist[t.classification] = dist.get(t.classification, 0) + 1
        db.execute("""INSERT OR REPLACE INTO ga4_page_trends
            (account_id, landing_page, n_days, sessions, slope, p_value, classification, current_engagement)
            VALUES (?,?,?,?,?,?,?,?)""",
            [acct, page, len(pts), int(total_sess), float(t.slope), float(t.p_value),
             t.classification, float(t.current_value)])
        n += 1
    db.execute("CHECKPOINT")
    return {"pages_with_trend": n, "distribution": dist}


def annotate_engagement_signals(db: Database) -> int:
    """Add the page's trajectory to engagement_drop / mobile signals so 'declining'
    (genuine degradation) is distinguished from 'stable/volatile' (always-low/noisy)."""
    import json
    sigs = db.fetchall("""SELECT signal_id, account_id, data_json, COALESCE(what_we_know,'')
                          FROM signals WHERE signal_type IN
                          ('ga4_engagement_drop','ga4_mobile_engagement_gap')""")
    annotated = 0
    for sid, acct, dj, wwk in sigs:
        page = (json.loads(dj) if dj else {}).get("landing_page", "")
        tr = db.fetchone("SELECT classification, slope FROM ga4_page_trends WHERE account_id=? AND landing_page=?",
                         [acct, page])
        if not tr:
            continue
        cls = tr[0]
        if "[trend]" in wwk:
            continue
        note = (f" [trend] page engagement is {cls}"
                + (" — genuine recent degradation." if cls == "declining"
                   else " — likely a persistent (not new) weakness." if cls in ("stable", "volatile")
                   else "."))
        db.execute("UPDATE signals SET what_we_know = what_we_know || ? WHERE signal_id=?", [note, sid])
        annotated += 1
    db.execute("CHECKPOINT")
    return annotated
