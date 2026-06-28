"""Run the GA4 x Google Ads cross-platform confidence-upgrade join."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.analysis.ga4_crossref import run_crossref

db = Database(); db.initialize()
# join hit rate (context)
hit = db.fetchone("""SELECT count(DISTINCT f.account_id||f.norm_path) FROM campaign_final_urls f
    WHERE EXISTS (SELECT 1 FROM ga4_landing_pages g WHERE g.account_id=f.account_id
                  AND g.landing_page=f.norm_path AND g.landing_page NOT IN ('(not set)','(other)',''))""")[0]
tot = db.fetchone("SELECT count(DISTINCT account_id||norm_path) FROM campaign_final_urls")[0]
print(f"[xref] URL join hit rate: {hit}/{tot} ({hit/tot*100:.0f}%) — capped by GA4 cardinality overflow on big accounts")

res = run_crossref(db)
print(f"[xref] Ads signals on matched accts examined: {res['examined']}")
print(f"[xref] with a joinable GA4 page: {res['joinable']}")
print(f"[xref] confidence UPGRADED to CONFIRMED: {res['upgraded']}")
print(f"[xref] by chain: {res['by_chain']}")
print(f"[xref] by signal type: {res['by_type']}")
print("\n[xref] sample upgraded links:")
for r in db.fetchall("""SELECT signal_type, campaign_id, matched_page, chain, ga4_evidence
                        FROM cross_platform_links WHERE new_tier='CONFIRMED' LIMIT 12"""):
    print(f"   [{r[3]}] {r[0]} camp {r[1]} -> {r[2][:36]} | {r[4][:80]}")
db.execute("CHECKPOINT")
print("\n[xref] DONE")
db.close()
