"""Phase 6.75 Fix — magnitude conditioning. The decisive test: does cost become
predictable (<15pp MAE) once templates know the budget change amount?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import permetric, magnitude

db = Database(); db.initialize()
eps = magnitude.attach_magnitude(db, permetric._episodes_with_deltas(db))
from collections import Counter
print(f"[fix] episodes: {len(eps)}")
print(f"[fix] magnitude buckets: {dict(Counter(e['magnitude_bucket'] for e in eps))}")

# budget bucket distribution (the test category)
budget = [e for e in eps if e["change_category"] == "budget"]
print(f"[fix] budget episodes by bucket: {dict(Counter(e['magnitude_bucket'] for e in budget))}")

# THE LOCK-IN TEST
print("\n[fix] === COST-MAE TEST (mechanical predictability) ===")
ct = magnitude.cost_mae_budget(eps)
cm = ct["category_cost_mae"]; mm = ct["magnitude_cost_mae"]
print(f"  budget cost MAE — category-only:   {cm*100:.0f}pp (n={ct['category_n']})" if cm else "  category: n/a")
print(f"  budget cost MAE — magnitude-cond:  {mm*100:.0f}pp (n={ct['magnitude_n']})" if mm else "  magnitude: n/a")
if cm and mm:
    print(f"  improvement: {(cm-mm)*100:+.0f}pp")
print(f"  PASSES <15pp lock-in: {ct['passes_15pp']}")

# full per-metric re-ranking with magnitude
print("\n[fix] === PER-METRIC RANKING (magnitude-conditioned, all categories) ===")
print(f"  {'metric':16} {'MAE':>7} {'exact+close':>12} {'n':>6}  tier")
for r in magnitude.predictability_ranking_mag(eps):
    print(f"  {r['metric']:16} {r['mae']*100:>5.0f}pp {r['exact_close_pct']*100:>10.0f}% {r['n']:>6}  {r['tier']}")

# persist magnitude-aware per-metric templates (for Phase 7)
pm = magnitude.per_metric_mag(db, eps)
print(f"\n[fix] magnitude-aware per-metric templates persisted: {len(pm)}")

# sample budget-increase forecast
print("\n[fix] === SAMPLE: budget medium_increase templates ===")
rows = db.fetchall("""SELECT template_id, metric, median_delta, iqr_low, iqr_high, mae, n
    FROM per_metric_predictions WHERE template_id LIKE 'mag:budget__mag=medium_increase%'
    ORDER BY template_id, mae LIMIT 18""")
cur = None
for tid, m, md, lo, hi, mae, n in rows:
    if tid != cur:
        print(f"  {tid.replace('mag:','')}"); cur = tid
    print(f"     {m:14} {md*100:>+5.0f}% ({lo*100:+.0f}% to {hi*100:+.0f}%)  MAE {mae*100:.0f}pp  n={n}")

db.execute("CHECKPOINT")
print("\n[fix] DONE")
db.close()
