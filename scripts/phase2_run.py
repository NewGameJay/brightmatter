"""Run the full Phase 2 pipeline end-to-end in one process, then verify the
final coherent state (single connection — avoids cross-process WAL staleness)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.analysis.trends import run_trends, profile_volatility
from brightmatter.analysis.regimes import run_regimes
from brightmatter.analysis.engine import AnalysisEngine
from brightmatter.patterns.episodes import EpisodeTracker

db = Database(); db.initialize(); repo = Repository(db)
t0 = time.time()

print("[p2] 2.1/2.5 trends + volatility…", flush=True)
nt = run_trends(db); profile_volatility(db)
print(f"[p2]   campaign_trends rows={nt} ({time.time()-t0:.0f}s)", flush=True)

print("[p2] 2.4 regimes…", flush=True)
nr = run_regimes(db)
print(f"[p2]   regime_changes={nr} ({time.time()-t0:.0f}s)", flush=True)

print("[p2] signals (2.2 annotation + 2.5 vol + 2.6 seasonal)…", flush=True)
db.execute("DELETE FROM signals"); db.execute("DELETE FROM patterns")
sigs = AnalysisEngine(db, repo).run_detectors_only()
print(f"[p2]   signals={len(sigs)} ({time.time()-t0:.0f}s)", flush=True)

print("[p2] 2.3 episodes (trend-adjusted)…", flush=True)
eps = EpisodeTracker(repo, db).process_episodes(reset=True)
db.execute("CHECKPOINT")
print(f"[p2]   episodes={len(eps)} ({time.time()-t0:.0f}s)", flush=True)

# Verify in-process (same connection, no stale read)
print("[p2] === COHERENT FINAL STATE (in-process) ===", flush=True)
print("[p2] signals trend_context set:", db.fetchone("SELECT count(*) FROM signals WHERE trend_context<>''")[0], flush=True)
print("[p2] episodes trend_adjusted:", db.fetchone("SELECT count(*) FROM episodes WHERE trend_adjusted")[0],
      "| confounded:", db.fetchone("SELECT count(*) FROM episodes WHERE confounded")[0], flush=True)
print("[p2] campaign_trends volatility set:", db.fetchone("SELECT count(*) FROM campaign_trends WHERE volatility_class<>''")[0], flush=True)
print("[p2] vertical_cpa_benchmark signals:", db.fetchone("SELECT count(*) FROM signals WHERE signal_type='vertical_cpa_benchmark'")[0], flush=True)
print("[p2] DONE", flush=True)
db.close()
