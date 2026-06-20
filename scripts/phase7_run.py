"""Phase 7 — proactive recommendation scan. Requires phase6_75_fix_run.py to have
persisted magnitude-aware per-metric templates ('mag:' rows)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import proactive

db = Database(); db.initialize()
scan = proactive.proactive_scan(db)

print(f"[p7] campaigns scanned (state known): {scan['campaigns_scanned']}")
print(f"[p7] recommendations: {len(scan['recommendations'])} | "
      f"warnings: {len(scan['warnings'])} | experiments: {len(scan['experiments'])}")

def fmt(r):
    ms = r["metrics"]
    return " ".join(f"{k}{ms[k][0]*100:+.0f}%" for k in ("cost","conversions","cpa","roas") if k in ms)

print("\n[p7] === TOP WARNINGS (do NOT do this) ===")
for w in scan["warnings"][:8]:
    print(f"  avoid {w['magnitude']:16} {w['action']:24} {w['campaign_id']:14} ({w['state']}) "
          f"cpa{w['cpa_median']*100:+.0f}% | {fmt(w)} n={w['n']}")

print("\n[p7] === TOP PATTERN-BACKED RECOMMENDATIONS ===")
for r in scan["recommendations"][:8]:
    print(f"  {r['magnitude']:16} {r['action']:24} {r['campaign_id']:14} ({r['state']}) "
          f"cpa{r['cpa_median']*100:+.0f}% | {fmt(r)} n={r['n']}")

print("\n[p7] === TOP EXPERIMENTS (knowledge gaps) ===")
for e in scan["experiments"][:8]:
    print(f"  test {e['suggested_magnitude']:16} {e['proposed_action']:24} in {e['state']:16} "
          f"({e['campaigns_in_gap']} campaigns) ")

doc = str(Path(__file__).resolve().parent.parent / "docs" / "brightmatter-proactive.md")
proactive.write_proactive_doc(db, doc, scan)
print(f"\n[p7] proactive doc -> {doc}")
db.execute("CHECKPOINT")
print("[p7] DONE")
db.close()
