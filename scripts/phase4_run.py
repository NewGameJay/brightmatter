"""Run Phase 4 (state-conditioned templates) end-to-end and print the catalog
summary, then the shadow simulation. Pass run_date via argv (no Date.now in core)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns.templates import run_templates, shadow_simulate, write_live_state_doc

RUN_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-06-19"

db = Database(); db.initialize()
res = run_templates(db, RUN_DATE)

print("\n[p4] === STATE DISTRIBUTION (4.0) ===")
total = sum(res["state_distribution"].values())
for st, n in sorted(res["state_distribution"].items(), key=lambda kv: -kv[1]):
    print(f"  {st:16} {n:5}  ({n/total*100:.0f}%)")

print(f"\n[p4] episodes used: {res['episodes_used']}")
print(f"[p4] templates extracted: {res['n_templates']}")
print(f"[p4] by status: {res['by_status']}")
print(f"[p4] by granularity level (0=sharpest): {res['by_level']}")

active = [t for t in res["templates"] if t["status"] == "ACTIVE"]
print(f"\n[p4] === TOP ACTIVE TEMPLATES (by direction accuracy) ===")
for t in sorted(active, key=lambda t: (-t['cv']['direction_accuracy'], -t['n_episodes']))[:25]:
    c = t["conditions"]
    cond = " ".join(f"{k}={v}" for k, v in c.items())
    cv = t["cv"]
    print(f"  [{cv['direction_accuracy']*100:3.0f}% dir, MAE {cv['magnitude_mae']*100:4.1f}pp] "
          f"pred={t['prediction_direction']} {t['prediction_magnitude']*100:+5.1f}% "
          f"n={t['n_episodes']:<3} acct={t['n_accounts']:<2} | {cond}")

print("\n[p4] === SHADOW SIMULATION (4.4, temporal holdout) ===")
sh = shadow_simulate(db)
print(f"  cutoff={sh['holdout_cutoff']} | train_eps={sh['train_episodes']} "
      f"holdout_eps={sh['holdout_episodes']} | templates_trained={sh['templates_trained']}")
print(f"  matched holdout episodes: {sh['matched']}")
print(f"  live direction accuracy:     {sh['live_direction_accuracy']*100:.0f}%")
print(f"  backtest direction accuracy: {sh['backtest_direction_accuracy']*100:.0f}%")
print(f"  magnitude buckets (live): {sh['buckets']}")

doc_path = str(Path(__file__).resolve().parent.parent / "docs" / "phase-4-live-state.md")
write_live_state_doc(db, doc_path, RUN_DATE)
print(f"\n[p4] live state doc -> {doc_path}")

db.execute("CHECKPOINT")
print("[p4] DONE")
db.close()
