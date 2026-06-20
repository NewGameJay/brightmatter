"""Run Phase 4.75: matched controls + act-vs-wait framework. Assumes Phase 4
(templates) and Phase 4.5 (baseline_observations, action_attributable) have run."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import actwait, refine

db = Database(); db.initialize()
eps = refine.refine_episodes(db)

# ── 4.75.1 matched controls ──
print("[p475] === 4.75.1 MATCHED CONTROLS (same campaign, same state) ===")
mc = actwait.build_matched_controls(db, eps)
print(f"  episodes: {mc['n_episodes']} | matched to a same-campaign no-action window: "
      f"{mc['n_matched']} ({mc['match_rate']*100:.0f}%)")
print(f"  {'state':16} {'matched_attribution':>20} {'n':>5}   (population from 4.5.1)")
pop = {"crisis": 0.07, "performing_well": 0.05, "struggling": 0.08, "stable": 0.09,
       "volatile": 0.05, "above_average": 0.00}
for st, s in sorted(mc["by_state"].items(), key=lambda kv: -kv[1]["n"]):
    popv = pop.get(st)
    pv = f"pop {popv*100:+.0f}pp" if popv is not None else ""
    print(f"  {st:16} {s['matched_median']*100:>+18.0f}pp {s['n']:>5}   {pv}")

# ── 4.75.3 act-vs-wait ──
print("\n[p475] === 4.75.3 TEMPLATE CATEGORIZATION ===")
cats = actwait.categorize_templates(db)
print(f"  do-nothing (action ~= natural): {len(cats['do_nothing'])}")
print(f"  don't-do-this (action >=10pp worse than waiting): {len(cats['dont_do_this'])}")
print(f"  act-now (action >=10pp better than waiting): {len(cats['act_now'])}")
print("\n  Top DON'T-DO-THIS (real action harm beyond gravity):")
for r in cats["dont_do_this"][:8]:
    print(f"    {r['template_id'][:52]:52} attrib {r['attributable']*100:+.0f}pp "
          f"(pred {r['pred_mag']*100:+.0f}% vs natural {r['natural']*100:+.0f}%) n={r['n']}")
if cats["act_now"]:
    print("\n  ACT-NOW (action genuinely beats waiting):")
    for r in cats["act_now"][:8]:
        print(f"    {r['template_id'][:52]:52} attrib {r['attributable']*100:+.0f}pp n={r['n']}")
else:
    print("\n  ACT-NOW: none — no template's action beats inaction by >=10pp.")

# ── recommendations for 10 campaigns ──
print("\n[p475] === ACT-VS-WAIT RECOMMENDATIONS (10 campaigns, action=budget) ===")
natural = actwait.natural_trajectory(db)
camps = db.fetchall("""
    SELECT e.account_id, e.campaign_id, COALESCE(a.account_name,''), count(*) n
    FROM episodes e LEFT JOIN accounts a ON a.account_id=e.account_id
    WHERE e.campaign_id <> '' GROUP BY 1,2,3 ORDER BY n DESC LIMIT 10
""")
for acct, camp, name, n in camps:
    d = actwait.should_act(db, acct, camp, "budget", natural=natural)
    print(f"\n  {name} ({d.get('vertical','?')}/{d.get('business_type','?')}) — state={d['state']}")
    if "do_nothing_forecast_pct" in d:
        print(f"    do-nothing forecast: CPA {d['do_nothing_forecast_pct']:+.0f}% | "
              f"with budget change: {d['template_prediction_pct']:+.0f}% | "
              f"action cost {d['action_cost_pp']:+.0f}pp")
        if d.get("matched_control"):
            print(f"    {d['matched_control']}")
    print(f"    >>> {d['decision']}: {d['reason']}")

db.execute("CHECKPOINT")
print("\n[p475] DONE")
db.close()
