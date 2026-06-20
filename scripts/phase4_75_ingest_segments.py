"""Phase 4.75 segment ingestion: device / search-partners / hour / day-of-week /
geographic / RSA ad-strength, window-aggregated per campaign (no segments.date, so
Google aggregates over the range — compact, one row per campaign×segment-value).

Resumable: completed accounts appended to /tmp/p475seg_done.txt and skipped.
Pass a single account id as argv[1] to test on one account first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from datetime import date, timedelta
from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.storage.database import Database

DAYS = 30
END = date.today()
START = END - timedelta(days=DAYS)
DONE = Path("/tmp/p475seg_done.txt")

# ── aggregated GAQL (no segments.date → aggregates over the window) ──
def q_metric_segment(seg_field):
    return (f"SELECT campaign.id, {seg_field}, metrics.impressions, metrics.clicks, "
            f"metrics.cost_micros, metrics.conversions FROM campaign "
            f"WHERE segments.date BETWEEN '{START}' AND '{END}' AND campaign.status != 'REMOVED'")

Q = {
    "device":  q_metric_segment("segments.device"),
    "network": q_metric_segment("segments.ad_network_type"),
    "hour":    q_metric_segment("segments.hour"),
    "dow":     q_metric_segment("segments.day_of_week"),
}
Q_GEO = (f"SELECT campaign.id, segments.geo_target_region, metrics.cost_micros, "
         f"metrics.conversions, metrics.impressions, metrics.clicks FROM geographic_view "
         f"WHERE segments.date BETWEEN '{START}' AND '{END}' AND metrics.cost_micros > 0")
# ad_strength is only meaningful for Responsive Search Ads; without this filter a
# Shopping account returns one "ad" per product (80k+), which hangs the pull.
Q_STRENGTH = ("SELECT campaign.id, ad_group.id, ad_group_ad.ad.id, ad_group_ad.ad_strength "
              "FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED' "
              "AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'")

ONE = sys.argv[1] if len(sys.argv) > 1 else None


def _seg_val(r, dim):
    if dim == "device":  return r.segments.device.name
    if dim == "network": return r.segments.ad_network_type.name
    if dim == "hour":    return str(r.segments.hour)
    if dim == "dow":     return r.segments.day_of_week.name
    return "?"


def ingest_account(db, client, acct):
    n = 0
    for dim, gaql in Q.items():
        try:
            rows = list(client.query(acct, gaql))
        except Exception as e:
            print(f"    {dim} ERROR {e}", flush=True); continue
        params = [(acct, str(r.campaign.id), dim, _seg_val(r, dim),
                   int(r.metrics.impressions), int(r.metrics.clicks),
                   int(r.metrics.cost_micros), float(r.metrics.conversions), START, END)
                  for r in rows]
        if params:
            db.conn.executemany("""INSERT OR REPLACE INTO campaign_segments
                (account_id,campaign_id,dimension,segment_value,impressions,clicks,
                 cost_micros,conversions,window_start,window_end) VALUES (?,?,?,?,?,?,?,?,?,?)""", params)
            n += len(params)
    # geo
    try:
        rows = list(client.query(acct, Q_GEO))
        params = [(acct, str(r.campaign.id), "geo", str(r.segments.geo_target_region),
                   int(r.metrics.impressions), int(r.metrics.clicks),
                   int(r.metrics.cost_micros), float(r.metrics.conversions), START, END)
                  for r in rows]
        if params:
            db.conn.executemany("""INSERT OR REPLACE INTO campaign_segments
                (account_id,campaign_id,dimension,segment_value,impressions,clicks,
                 cost_micros,conversions,window_start,window_end) VALUES (?,?,?,?,?,?,?,?,?,?)""", params)
            n += len(params)
    except Exception as e:
        print(f"    geo ERROR {e}", flush=True)
    # ad strength
    try:
        rows = list(client.query(acct, Q_STRENGTH))
        params = [(acct, str(r.campaign.id), str(r.ad_group.id), str(r.ad_group_ad.ad.id),
                   r.ad_group_ad.ad_strength.name) for r in rows]
        if params:
            db.conn.executemany("""INSERT OR REPLACE INTO ad_strength
                (account_id,campaign_id,ad_group_id,ad_id,ad_strength) VALUES (?,?,?,?,?)""", params)
            n += len(params)
    except Exception as e:
        print(f"    strength ERROR {e}", flush=True)
    return n


db = Database(); db.initialize()
client = GoogleAdsClient()

if ONE:
    print(f"[seg] TEST one account {ONE}", flush=True)
    print(f"[seg] inserted {ingest_account(db, client, ONE)} rows", flush=True)
    db.execute("CHECKPOINT")
    for dim, c in db.fetchall("SELECT dimension, count(*) FROM campaign_segments WHERE account_id=? GROUP BY 1", [ONE]):
        print(f"    {dim}: {c}", flush=True)
    print("    ad_strength:", db.fetchone("SELECT count(*) FROM ad_strength WHERE account_id=?", [ONE])[0], flush=True)
    db.close(); sys.exit(0)

accts = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]
done = set(l.strip() for l in DONE.read_text().splitlines()) if DONE.exists() else set()
print(f"[seg] {len(accts)} accounts, {len(done)} already done", flush=True)
import time; t0 = time.time()
with DONE.open("a") as df:
    for i, acct in enumerate(accts):
        if acct in done:
            continue
        try:
            n = ingest_account(db, client, acct)
            df.write(acct + "\n"); df.flush()
            print(f"[seg] {i+1}/{len(accts)} {acct}: {n} rows ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"[seg] {i+1}/{len(accts)} {acct}: ERROR {e}", flush=True)
db.execute("CHECKPOINT")
print(f"[seg] campaign_segments: {db.fetchone('SELECT count(*) FROM campaign_segments')[0]} | "
      f"ad_strength: {db.fetchone('SELECT count(*) FROM ad_strength')[0]}", flush=True)
print("[seg] DONE", flush=True)
db.close()
