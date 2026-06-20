"""4.5 — generate recommendations for the 10 campaigns with the richest episode
history, for marketer review. Programmatic: SQL match + stored template medians."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns.templates import recommend

db = Database(); db.initialize()

camps = db.fetchall("""
    SELECT e.account_id, e.campaign_id, COALESCE(a.account_name,''), count(*) n
    FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id
    WHERE e.campaign_id <> ''
    GROUP BY 1,2,3 ORDER BY n DESC LIMIT 10
""")

for acct, camp, name, n in camps:
    rec = recommend(db, acct, camp)
    print(f"\n{'='*78}")
    print(f"CAMPAIGN {camp} — {name} ({rec['vertical']}/{rec['spend_tier']}/{rec['business_type']})")
    print(f"Current state: {rec['state']}  | {n} historical episodes")
    rs = rec["recommendations"]
    if not rs:
        print("  No matching active templates for this campaign profile.")
        continue
    for r in rs[:5]:
        ma = " [multi-action]" if r["multi_action"] else ""
        rng = f"({r['range_pct'][0]:+.0f}% to {r['range_pct'][1]:+.0f}%)"
        print(f"  • {r['action']}{ma}: predicted CPA {r['direction']} "
              f"{r['magnitude_pct']:+.0f}% {rng}")
        print(f"      basis: {r['basis_episodes']} episodes / {r['basis_accounts']} accounts, "
              f"backtest {r['backtest_dir_acc']*100:.0f}% dir, MAE {r['mae_pct']:.0f}pp, "
              f"{r['status']} v{r['version']}")

db.close()
