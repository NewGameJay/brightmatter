"""Ingest GA4 Tier 1.1 landing-page engagement for the matched accounts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.ingestion.ga4 import run_ga4_ingestion

db = Database(); db.initialize()
res = run_ga4_ingestion(db, days=28, confidence="high")
print(f"[ga4] properties targeted: {res['properties']} | ingested: {res['ingested_ok']} "
      f"| skipped (bad impl): {res['skipped_impl']} | errors: {res['errors']}")
print(f"[ga4] landing-page rows: {res['rows']} ({res['elapsed_s']}s)")
print("[ga4] per property:")
for name, pid, status, n in res["per_property"]:
    print(f"   {name[:30]:30} {status:14} rows={n}")

# coverage summary
cov = db.fetchone("SELECT count(DISTINCT account_id), count(DISTINCT landing_page), count(*) FROM ga4_landing_pages")
print(f"\n[ga4] ga4_landing_pages: {cov[2]} rows across {cov[0]} accounts / {cov[1]} pages")
print("[ga4] implementation gate results:")
for r in db.fetchall("SELECT account_id, overall_engagement_rate, implementation_ok, note FROM ga4_property_health ORDER BY implementation_ok"):
    print(f"   acct {r[0]}: eng={r[1]} ok={r[2]} {r[3]}")
db.execute("CHECKPOINT")
print("[ga4] DONE")
db.close()
