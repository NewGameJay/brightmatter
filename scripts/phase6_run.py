"""Phase 6 historical simulations: cold start, reduced account, adversarial."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import simulate

db = Database(); db.initialize()

print("[p6] === 6.1 COLD START (build from zero, week by week) ===")
cs = simulate.cold_start(db)
print(f"  {'wk':>2} {'date':>12} {'train':>6} {'tmpl':>5} {'chg':>5} {'cov':>5} {'dir':>5} {'rec':>5}")
for r in cs:
    da = f"{r['direction_accuracy']*100:.0f}%" if r['direction_accuracy'] is not None else "  -"
    ra = f"{r['recommendation_accuracy']*100:.0f}%" if r['recommendation_accuracy'] is not None else "  -"
    print(f"  {r['week']:>2} {r['week_start']:>12} {r['train_episodes']:>6} {r['templates']:>5} "
          f"{r['changes']:>5} {r['coverage']*100:>4.0f}% {da:>5} {ra:>5}")
# inflection
useful = [r for r in cs if r['direction_accuracy'] and r['direction_accuracy'] >= 0.60 and r['coverage'] >= 0.50]
if useful:
    print(f"  INFLECTION: week {useful[0]['week']} ({useful[0]['week_start']}) — dir>=60% & coverage>=50%")
else:
    print("  INFLECTION: never reached both dir>=60% and coverage>=50% in-window")

print("\n[p6] === 6.2 REDUCED ACCOUNT (accuracy vs scale) ===")
ra = simulate.reduced_account(db)
print(f"  {'accts':>5} {'reps':>4} {'tmpl':>10} {'coverage':>9} {'active_dir_acc':>16}")
for r in ra:
    dacc = (f"{r['active_dir_acc_mean']*100:.0f}% ±{r['active_dir_acc_std']*100:.0f}"
            if r['active_dir_acc_mean'] is not None else "-")
    print(f"  {r['tier']:>5} {r['repeats']:>4} {r['templates_mean']:>6.0f}±{r['templates_std']:>3.0f} "
          f"{r['coverage_mean']*100:>7.0f}% {dacc:>16}")

print("\n[p6] === 6.3 ADVERSARIAL PERIODS ===")
adv = simulate.adversarial(db)
any2sd = any(d.get("above_2sd") for d in adv["disruptions"])
print(f"  weeks >=2sd above mean regime volume: {sum(1 for d in adv['disruptions'] if d.get('above_2sd'))}"
      f"{'' if any2sd else ' — none; showing top weeks by volume instead'}")
for w in adv["windows"]:
    def g(x): return f"{x['recommendation_accuracy']*100:.0f}%" if x and x.get('recommendation_accuracy') is not None else "-"
    def gd(x): return f"{x['direction_accuracy']*100:.0f}%" if x and x.get('direction_accuracy') is not None else "-"
    print(f"  week {w['disruption_week']} (regimes={w['regimes']}, accts={w['accounts']}, z={w['z']}):")
    print(f"     dir   pre={gd(w['pre'])} during={gd(w['during'])} post={gd(w['post'])}")
    print(f"     rec   pre={g(w['pre'])} during={g(w['during'])} post={g(w['post'])}")

db.close()
print("\n[p6] DONE")
