"""GA4 #6 — squirrelscan the cross-platform-CONFIRMED broken pages for the WHY.

GA4 + the cross-ref say which pages are broken (low/declining engagement, mobile gap).
squirrelscan says WHY (perf, mobile, images, SEO, technical). This audits each
distinct confirmed-broken page and stores the cause in ga4_page_audits, closing the
loop from "this page is the problem" to "here's what to fix."
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database

db = Database(); db.initialize()
rows = db.fetchall("""
    SELECT l.account_id, l.matched_page, COALESCE(MAX(f.domain), MAX(m.ga4_url)) dom
    FROM cross_platform_links l
    LEFT JOIN campaign_final_urls f ON f.account_id=l.account_id AND f.norm_path=l.matched_page
    LEFT JOIN ga4_property_map m ON m.account_id=l.account_id
    WHERE l.new_tier='CONFIRMED'
    GROUP BY 1,2""")
urls = {}
for acct, path, dom in rows:
    if dom:
        urls[f"https://{dom}{path}"] = acct
print(f"[sq] confirmed-broken pages to audit: {len(urls)}")

for url, acct in urls.items():
    tmp = tempfile.mktemp(suffix=".json")
    try:
        subprocess.run(["squirrel", "audit", url, "-C", "quick", "-f", "json", "-o", tmp],
                       capture_output=True, timeout=300)
        d = json.load(open(tmp))
    except Exception as e:  # noqa: BLE001
        print(f"[sq] {url}: ERROR {str(e)[:60]}"); continue
    sc = d.get("score", {})
    cats = {c["name"]: c["score"] for c in sc.get("categories", [])}
    summ = d.get("summary", {})
    issues = d.get("issues", [])
    top = [i.get("ruleId") for i in issues[:8]]
    db.execute("""INSERT OR REPLACE INTO ga4_page_audits
        (account_id, url, overall_score, grade, mobile_score, performance_score,
         failed_count, warnings_count, top_issues) VALUES (?,?,?,?,?,?,?,?,?)""",
        [acct, url, sc.get("overall"), sc.get("grade"), cats.get("Mobile"),
         cats.get("Performance"), summ.get("failed"), summ.get("warnings"), json.dumps(top)])
    print(f"[sq] {url}")
    print(f"     overall {sc.get('overall')}/{sc.get('grade')} | Mobile {cats.get('Mobile')} "
          f"Performance {cats.get('Performance')} Images {cats.get('Images')} | "
          f"{summ.get('failed')} failed / {summ.get('warnings')} warnings")
db.execute("CHECKPOINT")
print("[sq] DONE")
db.close()
