"""Phase 5 scheduler — the complete BrightMatter daily cycle.

Idempotent: predictions keyed deterministically (episode+template), resolutions
keyed (prediction,window). Safe to re-run; safe to run for consecutive as-of dates
to simulate continuous operation.

Usage:
  python scripts/daily_run.py                 # as-of = latest data date
  python scripts/daily_run.py 2026-06-10      # as-of override (simulate that day)

Ingestion (steps 1-2) is intentionally left to the existing scripts; this loop
covers PREDICT / RESOLVE / health / live-state on data already present.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import operate, refine

as_of = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None

db = Database(); db.initialize()
aod = as_of or operate._data_max_date(db)
print(f"[daily] === BrightMatter daily run · as-of {aod} ===")

# 3. PREDICT — register predictions for episodes (before outcome)
eps = refine.refine_episodes(db)
# only register episodes whose change is on/before as-of (no future leakage)
eps = [e for e in eps if e.get("change_date") and e["change_date"] <= aod]
n_reg = operate.register_predictions(db, eps)
print(f"[daily] registered predictions: {n_reg} (episodes <= as-of: {len(eps)})")

# 5. RESOLVE — score predictions whose windows have closed
res = operate.resolve_predictions(db, as_of=aod)
print(f"[daily] newly resolved: {res['newly_resolved']}")

# 6. UPDATE — template health
h = operate.update_template_health(db)
print(f"[daily] template health: scored {h['templates_scored']}, "
      f"promoted {h['promoted']}, demoted {h['demoted']}, drift {h['drift_alerts']}")

# 7. REPORT — live state doc
doc = str(Path(__file__).resolve().parent.parent / "docs" / "brightmatter-live-state.md")
operate.generate_live_state(db, doc)
rec = operate.recommendation_accuracy(db, 14)
if rec.get("n"):
    print(f"[daily] recommendation accuracy (14d, decisive): "
          f"{rec['decisive_recommendation_accuracy']*100:.0f}% (n={rec['decisive_n']}) | "
          f"abstain {rec['abstention_rate']*100:.0f}% | direction {rec['direction_accuracy']*100:.0f}%")
print(f"[daily] live state -> {doc}")

db.execute("CHECKPOINT")
print("[daily] DONE")
db.close()
