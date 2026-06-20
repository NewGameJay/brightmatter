"""GA4 Phase 1 (completion) — precise property -> Ads account mapping.

Metadata only (Admin API: accountSummaries + per-property dataStreams for the website
URL). Pulls NO GA4 report data — stays within Phase 1's boundary. Matches the 230
visible GA4 properties to the 223 active Ads accounts by website domain (high
confidence), with a name-token fallback (low confidence). Persists ga4_property_map.
"""
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import requests
from brightmatter.storage.database import Database

ADMIN = "https://analyticsadmin.googleapis.com/v1beta"


def _domain(u: str) -> str:
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = u.split("/")[0].split("?")[0]
    u = re.sub(r"^www\.", "", u)
    return u


def _tok(s: str) -> set:
    stop = {"ga4", "http", "https", "www", "com", "remove", "global", "old", "test",
            "google", "analytics", "paid", "account", "ads", "media", "the", "and"}
    return set(re.findall(r"[a-z0-9]{4,}", (s or "").lower())) - stop


def main() -> int:
    cid, csec = os.getenv("GOOGLE_ADS_CLIENT_ID"), os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    rt = os.getenv("GA4_REFRESH_TOKEN")
    at = requests.post("https://oauth2.googleapis.com/token",
                       data={"client_id": cid, "client_secret": csec,
                             "refresh_token": rt, "grant_type": "refresh_token"},
                       timeout=20).json().get("access_token")
    if not at:
        print("ERROR: could not mint GA4 token from .env", file=sys.stderr); return 1
    H = {"Authorization": f"Bearer {at}"}

    # 1. list properties
    props = []
    for a in requests.get(f"{ADMIN}/accountSummaries", headers=H, timeout=40).json().get("accountSummaries", []):
        for p in a.get("propertySummaries", []):
            props.append((p.get("property"), p.get("displayName", "")))
    print(f"[map] GA4 properties visible: {len(props)}", flush=True)

    # 2. per-property web-stream URL (metadata)
    prop_url = {}
    t0 = time.time()
    for i, (pid, _) in enumerate(props):
        try:
            streams = requests.get(f"{ADMIN}/{pid}/dataStreams", headers=H, timeout=30).json().get("dataStreams", [])
            for s in streams:
                uri = (s.get("webStreamData") or {}).get("defaultUri")
                if uri:
                    prop_url[pid] = _domain(uri)
                    break
        except Exception:
            pass
        if (i + 1) % 60 == 0:
            print(f"[map] streams {i+1}/{len(props)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"[map] properties with a web URL: {len(prop_url)} ({time.time()-t0:.0f}s)", flush=True)

    # index: domain -> property
    by_domain = {}
    for pid, dom in prop_url.items():
        by_domain.setdefault(dom, pid)
    name_by_pid = dict(props)

    # 3. match accounts
    db = Database(); db.initialize()
    accts = db.fetchall("""
        SELECT account_id, COALESCE(account_name,''), COALESCE(website_url,'')
        FROM accounts WHERE account_id IN (SELECT DISTINCT account_id FROM daily_metrics)""")
    db.execute("DELETE FROM ga4_property_map")
    url_hi = name_lo = none = 0
    for aid, name, url in accts:
        dom = _domain(url)
        pid = by_domain.get(dom) if dom else None
        method, conf, gp, gu = "unmatched", "none", None, None
        if pid:
            method, conf, gp, gu = "url_domain", "high", pid, dom
            url_hi += 1
        else:
            # name-token fallback: require >=2 shared meaningful tokens (precision)
            at_t = _tok(name)
            best = None
            for ppid, pname in props:
                shared = at_t & _tok(pname)
                if len(shared) >= 2:
                    best = ppid; break
            if best:
                method, conf, gp, gu = "name_token", "low", best, prop_url.get(best)
                name_lo += 1
            else:
                none += 1
        db.execute("""INSERT OR REPLACE INTO ga4_property_map
            (account_id, account_name, account_url, ga4_property, ga4_name, ga4_url,
             match_method, match_confidence) VALUES (?,?,?,?,?,?,?,?)""",
            [aid, name, url, gp, name_by_pid.get(gp) if gp else None, gu, method, conf])
    db.execute("CHECKPOINT")

    n = len(accts)
    print(f"\n[map] === MAPPING COVERAGE ({n} active accounts) ===")
    print(f"  high-confidence URL-domain match: {url_hi} ({url_hi/n*100:.0f}%)")
    print(f"  low-confidence name-token match:  {name_lo} ({name_lo/n*100:.0f}%)")
    print(f"  unmatched:                        {none} ({none/n*100:.0f}%)")
    print("\n[map] sample high-confidence matches:")
    for r in db.fetchall("""SELECT account_name, ga4_url, ga4_name FROM ga4_property_map
                            WHERE match_confidence='high' LIMIT 12"""):
        print(f"   {r[0][:30]:30} -> {(r[1] or '')[:28]:28} ({r[2]})")
    db.close()
    print("\n[map] DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
