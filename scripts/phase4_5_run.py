"""Run Phase 4.5 (refinement layers) and print findings. Assumes Phase 4 has
populated the templates catalog (scripts/phase4_run.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns import refine

db = Database(); db.initialize()
eps = refine.refine_episodes(db)
print(f"[p45] refine episodes: {len(eps)}")

# ── 4.5.1 mean reversion ──
print("\n[p45] === 4.5.1 MEAN-REVERSION CONTROL ===")
mr = refine.mean_reversion_control(db, eps)
print(f"  {'state':16} {'action_med':>11} {'natural_med':>12} {'attributable':>13}  (n act/nat)")
for st, s in sorted(mr.items(), key=lambda kv: -(kv[1]['action_n'])):
    am = f"{s['action_median']*100:+.0f}%" if s['action_median'] is not None else "  -"
    nm = f"{s['natural_median']*100:+.0f}%" if s['natural_median'] is not None else "  -"
    at = f"{s['action_attributable']*100:+.0f}pp" if s['action_attributable'] is not None else "  -"
    print(f"  {st:16} {am:>11} {nm:>12} {at:>13}  ({s['action_n']}/{s['natural_n']})")

# ── 4.5.2 exceptions ──
print("\n[p45] === 4.5.2 CONDITIONAL EXCEPTIONS ===")
exc = refine.mine_exceptions(db, eps, top_n=12)
flips = [e for e in exc if e["flips"]]
print(f"  exceptions found: {len(exc)} (direction-flipping: {len(flips)})")
for e in exc[:12]:
    flip = "FLIPS" if e["flips"] else "shifts"
    print(f"  • [{flip}] {e['template_id']}")
    print(f"      when {e['exception_dim']}={e['exception_value']}: base predicts {e['base_prediction']}, "
          f"exception {e['exception_direction']} {e['exception_magnitude']*100:+.0f}% "
          f"(n={e['n_exception']}/{e['n_accounts']}acct, p={e['p_value']:.3f})")

# ── 4.5.3 transfer ──
print("\n[p45] === 4.5.3 CROSS-ACCOUNT TRANSFER ===")
tr = refine.transfer_test(db, eps)
print(f"  holdout accounts (20+ eps): {tr['holdout_accounts']} | matched episodes: {tr['matched_episodes']}")
print(f"  transfer direction accuracy: {tr['transfer_accuracy']*100:.0f}%  (backtest baseline ~67%)")
print(f"  by business_type:")
for b, (acc, n) in sorted(tr["by_business_type"].items(), key=lambda kv: -kv[1][0]):
    print(f"    {b:14} {acc*100:.0f}% (n={n})")
print(f"  worst-transfer accounts:")
for p in tr["worst_accounts"]:
    print(f"    {p['account_id']}: {p['accuracy']*100:.0f}% (matched {p['matched']})")

# ── 4.5.4 magnitude convergence ──
print("\n[p45] === 4.5.4 MAGNITUDE CONVERGENCE ===")
conv = refine.magnitude_convergence(db, eps, top_n=10)
print(f"  templates tracked: {len(conv)} | converging (late MAE < early): "
      f"{sum(1 for c in conv if c['converging'])}/{len(conv)}")
for c in conv:
    # compact MAE-vs-observation sparkline at fixed checkpoints
    pts = {n: m for n, m in c["curve"]}
    checks = [n for n in (5, 10, 25, 50, 100) if n <= c["n"]]
    spark = " ".join(f"@{n}:{pts[max(k for k in pts if k<=n)]*100:.0f}pp" for n in checks)
    arrow = "↓converging" if c["converging"] else "→flat/noisy"
    print(f"  {c['template_id'][:48]:48} n={c['n']:<3} {arrow}  {spark}")

db.execute("CHECKPOINT")
print("\n[p45] DONE")
db.close()
