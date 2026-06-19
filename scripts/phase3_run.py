"""Run Phase 3 (segment-scoped learning) end-to-end and print the synthesis.

Assumes Phase 2 has already populated episodes (with trend adjustment). Computes
segments / segment_patterns / segment_comparisons, then prints pattern cards and
Phase 4 promotion candidates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.patterns.segments import run_segments

db = Database(); db.initialize()
res = run_segments(db)

print(f"\n[p3] clean (non-confounded) episodes: {res['clean_episodes']}")
print(f"[p3] segments enumerated: {len(res['segments'])}")
print(f"[p3] segment patterns (>= directional n): {len(res['patterns'])}")
print(f"[p3] segment comparisons: {len(res['comparisons'])}")
sig = [c for c in res["comparisons"] if c["significant"]]
print(f"[p3]   of which significant (p<0.05): {len(sig)}")

print("\n[p3] === TOP SEGMENT PATTERN CARDS (reliable/directional) ===")
for c in res["cards"][:25]:
    vs = ""
    if c["vs_rest"]:
        v = c["vs_rest"]
        star = " *SIG*" if v["significant"] else ""
        vs = (f"  | vs rest {v['rest_rate']*100:.0f}% (Δ{v['delta']*100:+.0f}pp, "
              f"p={v['p_value']:.3f}){star}")
    print(f"  [{c['confidence']:11}] {c['segment']:28} {c['change']:34} "
          f"n={c['n']:<4} acct={c['accounts']:<3} "
          f"deg={c['degraded_rate']*100:.0f}% CI[{c['degraded_ci'][0]*100:.0f}-{c['degraded_ci'][1]*100:.0f}]{vs}")

print(f"\n[p3] === PHASE 4 PROMOTION CANDIDATES ({len(res['promotion_candidates'])}) ===")
for cand in res["promotion_candidates"]:
    print(f"  • {cand['claim']}")
    print(f"    (n={cand['n']}, accounts={cand['accounts']})")

db.execute("CHECKPOINT")
print("\n[p3] DONE")
db.close()
