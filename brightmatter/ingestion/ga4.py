"""GA4 ingestion — Tier 1.1 landing-page engagement (research/ga4 signal map).

Uses the GA4 Data API REST endpoint (analyticsdata.googleapis.com runReport) with
the info@hawkemedia.com OAuth token. Session scope only (landingPage is inherently
session-scoped — the safe scope per Farina/the API doc).

Includes the expert-mandated implementation-quality gate (Ahava/Seiden/Fedorovicius:
most GA4 setups are broken). A property that fires a key event on every pageview
shows ~100% engagement and inflated session CVR — its engagement signal is
meaningless. We measure overall engagement + key-events/session first and flag
properties that look misconfigured before trusting their per-page data.
"""

from __future__ import annotations

import os
import re
import time
from datetime import date

import requests

from brightmatter.storage.database import Database

DATA_API = "https://analyticsdata.googleapis.com/v1beta"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# implementation-quality gate
SUSPICIOUS_ENGAGEMENT = 0.97     # >=97% overall engagement => key_event likely on every view
MIN_SESSIONS_FOR_PAGE = 50       # research minimum (per week); we ingest 28d so ~ x4


def mint_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.getenv("GA4_REFRESH_TOKEN"),
        "grant_type": "refresh_token"}, timeout=20)
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"GA4 token mint failed: {j.get('error_description', j)}")
    return j["access_token"]


def normalize_path(landing_page: str) -> str:
    """GA4 landingPage is already a path; strip query + trailing slash, lowercase."""
    p = (landing_page or "").split("?")[0].rstrip("/").lower()
    return p or "/"


def _run_report(token: str, pid: str, body: dict) -> dict:
    r = requests.post(f"{DATA_API}/{pid}:runReport",
                      headers={"Authorization": f"Bearer {token}"}, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"runReport {pid} -> {r.status_code}: {str(r.json())[:200]}")
    return r.json()


def check_implementation(db: Database, token: str, pid: str, account_id: str, days: int = 28) -> bool:
    """Property-level engagement + key-events/session. Flags misconfigured properties
    (engagement pinned near 100% = a key_event fires on every view). Returns ok bool."""
    j = _run_report(token, pid, {
        "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                    {"name": "engagementRate"}, {"name": "keyEvents"}],
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
    })
    rows = j.get("rows", [])
    if not rows:
        db.execute("""INSERT OR REPLACE INTO ga4_property_health
            (ga4_property, account_id, overall_engagement_rate, key_events_per_session,
             implementation_ok, note) VALUES (?,?,?,?,?,?)""",
            [pid, account_id, None, None, False, "no sessions in window"])
        return False
    m = rows[0]["metricValues"]
    sessions = float(m[0]["value"]) or 1
    eng_rate = float(m[2]["value"])
    ke_per_sess = float(m[3]["value"]) / sessions
    ok = eng_rate < SUSPICIOUS_ENGAGEMENT
    note = "" if ok else f"engagement {eng_rate:.2f} >= {SUSPICIOUS_ENGAGEMENT} (key_event likely on every view)"
    db.execute("""INSERT OR REPLACE INTO ga4_property_health
        (ga4_property, account_id, overall_engagement_rate, key_events_per_session,
         implementation_ok, note) VALUES (?,?,?,?,?,?)""",
        [pid, account_id, eng_rate, ke_per_sess, ok, note])
    return ok


def ingest_landing_pages(db: Database, token: str, pid: str, account_id: str, days: int = 28) -> int:
    """Landing-page × device engagement over the window. One paginated runReport."""
    inserted = 0
    offset = 0
    while True:
        j = _run_report(token, pid, {
            "dimensions": [{"name": "landingPage"}, {"name": "deviceCategory"}, {"name": "date"}],
            "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                        {"name": "engagementRate"}, {"name": "bounceRate"},
                        {"name": "averageSessionDuration"}, {"name": "sessionConversionRate"},
                        {"name": "keyEvents"}, {"name": "totalRevenue"}],
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "limit": 10000, "offset": offset,
        })
        rows = j.get("rows", [])
        if not rows:
            break
        params = []
        for rw in rows:
            d = [x["value"] for x in rw["dimensionValues"]]
            m = [x["value"] for x in rw["metricValues"]]
            lp = normalize_path(d[0])
            dev = d[1].lower()
            dt = f"{d[2][:4]}-{d[2][4:6]}-{d[2][6:8]}"   # YYYYMMDD -> YYYY-MM-DD
            # m is already the list of string values
            params.append((pid, account_id, dt, lp, dev,
                           int(float(m[0])), int(float(m[1])),
                           float(m[2]), float(m[3]), float(m[4]),
                           float(m[5]), float(m[6]), float(m[7])))
        # aggregate dup (path collisions after normalization) via INSERT OR REPLACE
        db.conn.executemany("""INSERT OR REPLACE INTO ga4_landing_pages
            (ga4_property, account_id, date, landing_page, device, sessions, engaged_sessions,
             engagement_rate, bounce_rate, avg_session_duration, session_cvr, key_events, revenue)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", params)
        inserted += len(params)
        offset += len(rows)
        if len(rows) < 10000:
            break
    return inserted


def ingest_landing_pages_filtered(db: Database, token: str, pid: str, account_id: str,
                                  paths: list[str], days: int = 28) -> int:
    """Targeted ingest: pull landingPage engagement for a SPECIFIC list of paths via a
    dimensionFilter. Filtering keeps cardinality low, so high-traffic properties that
    otherwise collapse into '(other)' return real per-page data. Batches the path list."""
    inserted = 0
    BATCH = 100
    for i in range(0, len(paths), BATCH):
        chunk = paths[i:i + BATCH]
        j = _run_report(token, pid, {
            "dimensions": [{"name": "landingPage"}, {"name": "deviceCategory"}, {"name": "date"}],
            "metrics": [{"name": "sessions"}, {"name": "engagedSessions"},
                        {"name": "engagementRate"}, {"name": "bounceRate"},
                        {"name": "averageSessionDuration"}, {"name": "sessionConversionRate"},
                        {"name": "keyEvents"}, {"name": "totalRevenue"}],
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
            "dimensionFilter": {"filter": {"fieldName": "landingPage",
                                           "inListFilter": {"values": chunk}}},
            "limit": 10000,
        })
        params = []
        for rw in j.get("rows", []):
            d = [x["value"] for x in rw["dimensionValues"]]
            m = [x["value"] for x in rw["metricValues"]]
            lp = normalize_path(d[0]); dev = d[1].lower()
            dt = f"{d[2][:4]}-{d[2][4:6]}-{d[2][6:8]}"
            params.append((pid, account_id, dt, lp, dev,
                           int(float(m[0])), int(float(m[1])), float(m[2]), float(m[3]),
                           float(m[4]), float(m[5]), float(m[6]), float(m[7])))
        if params:
            db.conn.executemany("""INSERT OR REPLACE INTO ga4_landing_pages
                (ga4_property, account_id, date, landing_page, device, sessions, engaged_sessions,
                 engagement_rate, bounce_rate, avg_session_duration, session_cvr, key_events, revenue)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", params)
            inserted += len(params)
    return inserted


def run_filtered_ingestion(db: Database, days: int = 28) -> dict:
    """For each matched account, ingest its campaigns' final-URL paths via filtered
    queries — recovers pages that cardinality overflow hid on high-traffic properties."""
    token = mint_token()
    rows = db.fetchall("""
        SELECT m.account_id, m.ga4_property, list(DISTINCT f.norm_path)
        FROM ga4_property_map m JOIN campaign_final_urls f ON f.account_id = m.account_id
        WHERE m.match_confidence='high' AND m.ga4_property IS NOT NULL AND f.norm_path IS NOT NULL
        GROUP BY 1,2""")
    summary = {"accounts": len(rows), "rows": 0, "per_account": []}
    for acct, pid, paths in rows:
        paths = [p for p in paths if p]
        try:
            n = ingest_landing_pages_filtered(db, token, pid, acct, paths, days)
        except Exception as e:  # noqa: BLE001
            summary["per_account"].append((acct, f"ERROR {str(e)[:50]}", 0)); continue
        summary["rows"] += n
        summary["per_account"].append((acct, "ok", n))
    db.execute("CHECKPOINT")
    return summary


def ingest_source_engagement(db: Database, token: str, pid: str, account_id: str, days: int = 28) -> int:
    """Channel-group engagement (Domain 5). Low cardinality — no overflow risk."""
    j = _run_report(token, pid, {
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
        "metrics": [{"name": "sessions"}, {"name": "engagementRate"},
                    {"name": "bounceRate"}, {"name": "sessionConversionRate"}],
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
    })
    params = []
    for rw in j.get("rows", []):
        ch = rw["dimensionValues"][0]["value"]
        m = [x["value"] for x in rw["metricValues"]]
        params.append((pid, account_id, ch, int(float(m[0])), float(m[1]), float(m[2]), float(m[3])))
    if params:
        db.conn.executemany("""INSERT OR REPLACE INTO ga4_source_engagement
            (ga4_property, account_id, channel, sessions, engagement_rate, bounce_rate, session_cvr)
            VALUES (?,?,?,?,?,?,?)""", params)
    return len(params)


def run_source_ingestion(db: Database, days: int = 28) -> dict:
    token = mint_token()
    targets = db.fetchall("""SELECT account_id, ga4_property FROM ga4_property_map
                             WHERE match_confidence='high' AND ga4_property IS NOT NULL""")
    n = rows = 0
    for acct, pid in targets:
        try:
            rows += ingest_source_engagement(db, token, pid, acct, days); n += 1
        except Exception:
            pass
    db.execute("CHECKPOINT")
    return {"properties": n, "rows": rows}


def run_ga4_ingestion(db: Database, days: int = 28, confidence: str = "high") -> dict:
    """Ingest landing-page engagement for the mapped GA4 properties (default: the
    high-confidence matches). Runs the implementation gate first."""
    token = mint_token()
    targets = db.fetchall(f"""
        SELECT account_id, account_name, ga4_property FROM ga4_property_map
        WHERE ga4_property IS NOT NULL AND match_confidence = ?""", [confidence])
    summary = {"properties": len(targets), "ingested_ok": 0, "skipped_impl": 0,
               "rows": 0, "errors": 0, "per_property": []}
    t0 = time.time()
    for acct, name, pid in targets:
        try:
            ok = check_implementation(db, token, pid, acct, days)
            if not ok:
                summary["skipped_impl"] += 1
                summary["per_property"].append((name, pid, "SKIP impl", 0))
                continue
            n = ingest_landing_pages(db, token, pid, acct, days)
            summary["ingested_ok"] += 1
            summary["rows"] += n
            summary["per_property"].append((name, pid, "ok", n))
        except Exception as e:  # noqa: BLE001
            summary["errors"] += 1
            summary["per_property"].append((name, pid, f"ERROR {str(e)[:60]}", 0))
    db.execute("CHECKPOINT")
    summary["elapsed_s"] = round(time.time() - t0)
    return summary
