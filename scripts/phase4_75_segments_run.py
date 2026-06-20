"""Phase 4.75 segment analysis: emit the 5 segment detector signals, attach
segment attributes to episodes, and re-run exception mining with the new
dimensions. Assumes scripts/phase4_75_ingest_segments.py has populated
campaign_segments + ad_strength, and Phase 4 templates exist."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.analysis import segment_detectors as SD
from brightmatter.patterns import refine

db = Database(); db.initialize(); repo = Repository(db)

# ── coverage ──
cs = db.fetchone("SELECT count(*), count(DISTINCT account_id||campaign_id) FROM campaign_segments")
ast = db.fetchone("SELECT count(*), count(DISTINCT account_id||campaign_id) FROM ad_strength")
print(f"[seg] campaign_segments: {cs[0]} rows / {cs[1]} campaigns | ad_strength: {ast[0]} RSAs / {ast[1]} campaigns")

# ── 5 detectors -> signals ──
db.execute("DELETE FROM signals WHERE signal_type IN "
           "('device_mobile_drag','search_partners_waste','dead_zone_spend','geo_cpa_outlier','weak_ad_strength')")
sigs = SD.detect_segment_signals(db)
for s in sigs:
    repo.insert_signal(s)
db.execute("CHECKPOINT")
print(f"[seg] segment signals emitted: {len(sigs)}")
print(f"[seg] by type: {dict(Counter(s.signal_type for s in sigs))}")

# ── attach segment attributes to episodes ──
feats = SD.compute_campaign_segment_features(db)
eps = refine.refine_episodes(db)
covered = 0
for e in eps:
    f = feats.get((e["account_id"], e["campaign_id"]))
    attrs = SD.episode_segment_attributes(f) if f else {
        "device_profile": "unknown", "mobile_cvr_drag": "unknown", "partners_exposed": "unknown",
        "dead_zones": "unknown", "geo_variance": "unknown", "ad_quality": "unknown"}
    e.update(attrs)
    if f:
        covered += 1
print(f"[seg] episodes with segment features attached: {covered}/{len(eps)}")
SEG_DIMS = ("device_profile", "mobile_cvr_drag", "partners_exposed",
            "dead_zones", "geo_variance", "ad_quality")
for d in SEG_DIMS:
    print(f"  {d}: {dict(Counter(e.get(d,'unknown') for e in eps))}")

# ── re-run exception mining with original + segment dimensions ──
DIMS = refine._EXC_DIMENSIONS + SEG_DIMS
exc = refine.mine_exceptions(db, eps, top_n=15, dims=DIMS)
seg_exc = [x for x in exc if x["exception_dim"] in SEG_DIMS]
print(f"\n[seg] === EXCEPTION MINING (re-run with {len(SEG_DIMS)} new segment dims) ===")
print(f"  total exceptions at rigorous bar (10+ eps / 3+ accts / p<0.05): {len(exc)}")
print(f"  of which on a NEW segment dimension: {len(seg_exc)}")
for e in exc[:15]:
    flip = "FLIPS" if e["flips"] else "shifts"
    star = " *SEGMENT*" if e["exception_dim"] in SEG_DIMS else ""
    print(f"  • [{flip}{star}] {e['template_id'][:46]}")
    print(f"      when {e['exception_dim']}={e['exception_value']}: base {e['base_prediction']} → "
          f"{e['exception_direction']} {e['exception_magnitude']*100:+.0f}% "
          f"(n={e['n_exception']}/{e['n_accounts']}acct, p={e['p_value']:.3f})")

db.execute("CHECKPOINT")
print("\n[seg] DONE")
db.close()
