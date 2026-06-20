"""Phase 6.75 — per-metric template predictions + hypothesis loop."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import permetric

db = Database(); db.initialize()
eps = permetric._episodes_with_deltas(db)
print(f"[p675] episodes with per-metric deltas: {len(eps)}")

# 6.75.2 reshape
pmt = permetric.per_metric_templates(db, eps)
print(f"[p675] templates with per-metric predictions: {len(pmt)}")

# 6.75.3 predictability ranking — the headline
print("\n[p675] === METRIC PREDICTABILITY RANKING ===")
print(f"  {'metric':16} {'MAE':>7} {'exact+close':>12} {'n':>6}  tier")
for r in permetric.predictability_ranking(db, eps):
    print(f"  {r['metric']:16} {r['mae']*100:>5.0f}pp {r['exact_close_pct']*100:>10.0f}% "
          f"{r['n']:>6}  {r['tier']}")

# 6.75.4 register + resolve hypotheses
n_reg = permetric.register_metric_hypotheses(db, eps)
res = permetric.resolve_metric_hypotheses(db, eps)
print(f"\n[p675] === HYPOTHESIS LOOP ===")
print(f"  metric predictions registered: {n_reg} | resolved: {res['resolved']}")
print(f"  {'metric':16} {'n':>6} {'MAE':>7} {'within_IQR':>11}")
for m, s in sorted(res["by_metric"].items(), key=lambda kv: kv[1]["mae"]):
    print(f"  {m:16} {s['n']:>6} {s['mae']*100:>5.0f}pp {s['within_iqr']*100:>9.0f}%")

# sample recommendation forecast
print("\n[p675] === SAMPLE PER-METRIC FORECAST ===")
camp = db.fetchone("""SELECT e.account_id, e.campaign_id, COALESCE(a.account_name,''), count(*) n
    FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id
    WHERE e.campaign_id<>'' GROUP BY 1,2,3 ORDER BY n DESC LIMIT 1""")
fc = permetric.recommendation_metric_forecast(db, camp[0], camp[1])
if fc:
    print(f"  {camp[2]} — state={fc['state']}, action={fc['action']}{' (multi)' if fc['multi'] else ''}")
    print(f"  template: {fc['template_id']}")
    print(f"  {'metric':16} {'median':>8} {'range':>20} {'MAE':>7} {'n':>5}")
    for m in fc["metrics"]:
        rng = f"({m['low']*100:+.0f}% to {m['high']*100:+.0f}%)"
        print(f"  {m['metric']:16} {m['median']*100:>+7.0f}% {rng:>20} {m['mae']*100:>5.0f}pp {m['n']:>5}")

db.execute("CHECKPOINT")
print("\n[p675] DONE")
db.close()
