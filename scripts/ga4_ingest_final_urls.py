"""Ingest Google Ads campaign final URLs for the GA4<->Ads page join.

Pulls ad-level final_urls (Search/Display/Demand Gen/Video — filtered to dodge the
Shopping ad_group_ad row explosion) + asset_group final_urls (PMax). Shopping has no
campaign final_url (it comes from the Merchant Center feed) — those campaigns get no
row (expected gap). Scoped to the 12 GA4-matched accounts, where the join matters.
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.storage.database import Database

Q_ADS = ("SELECT campaign.id, campaign.advertising_channel_type, ad_group_ad.ad.final_urls "
         "FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED' "
         "AND campaign.advertising_channel_type IN ('SEARCH','DISPLAY','DEMAND_GEN','VIDEO')")
Q_PMAX = ("SELECT campaign.id, asset_group.final_urls FROM asset_group "
          "WHERE asset_group.status != 'REMOVED'")


def norm(u: str):
    if not u:
        return None, None
    low = u.strip().lower()
    dom = re.sub(r"^https?://", "", low).split("/")[0].split("?")[0]
    dom = re.sub(r"^www\.", "", dom)
    path = re.sub(r"^https?://[^/]+", "", low).split("?")[0].rstrip("/").lower() or "/"
    return path, dom


db = Database(); db.initialize()
client = GoogleAdsClient()
accts = db.fetchall("SELECT account_id, account_name FROM ga4_property_map WHERE match_confidence='high'")
print(f"[fu] ingesting final URLs for {len(accts)} matched accounts", flush=True)

t0 = time.time()
total = 0
for i, (aid, name) in enumerate(accts):
    seen = set()
    params = []
    for q, src, getter in (
        (Q_ADS, "ad_group_ad", lambda r: (str(r.campaign.id), r.campaign.advertising_channel_type.name, list(r.ad_group_ad.ad.final_urls))),
        (Q_PMAX, "asset_group", lambda r: (str(r.campaign.id), "PERFORMANCE_MAX", list(r.asset_group.final_urls))),
    ):
        try:
            for r in client.query(aid, q):
                cid, ch, urls = getter(r)
                for u in urls:
                    key = (cid, u)
                    if key in seen:
                        continue
                    seen.add(key)
                    p, d = norm(u)
                    params.append((aid, cid, ch, u, p, d, src))
        except Exception as e:  # noqa: BLE001
            print(f"[fu] {name}: {src} ERROR {str(e)[:70]}", flush=True)
    if params:
        db.conn.executemany("""INSERT OR REPLACE INTO campaign_final_urls
            (account_id, campaign_id, channel, final_url, norm_path, domain, source)
            VALUES (?,?,?,?,?,?,?)""", params)
        total += len(params)
    camps = len({p[1] for p in params})
    print(f"[fu] {i+1}/{len(accts)} {name[:28]:28} urls={len(params)} campaigns={camps} ({time.time()-t0:.0f}s)", flush=True)
db.execute("CHECKPOINT")

print(f"\n[fu] total final-url rows: {total}")
cov = db.fetchone("SELECT count(DISTINCT account_id), count(DISTINCT campaign_id), count(*) FROM campaign_final_urls")
print(f"[fu] coverage: {cov[1]} campaigns / {cov[0]} accounts / {cov[2]} urls")
print("[fu] by channel:", dict(db.fetchall("SELECT channel, count(DISTINCT campaign_id) FROM campaign_final_urls GROUP BY 1")))
print("[fu] DONE")
db.close()
