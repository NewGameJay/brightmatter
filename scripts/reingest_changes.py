"""Re-pull change history (28d) for all ingested accounts — fixes auto_applied."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.ingestion.pipeline import IngestionPipeline
db = Database(); db.initialize(); repo = Repository(db)
pipe = IngestionPipeline(repo)
ids = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]
print(f"[changes] re-pulling 28d change history for {len(ids)} accounts", flush=True)
t0 = time.time(); total = 0; ok = 0
for i, aid in enumerate(ids):
    try:
        ch = pipe.ingest_changes(account_ids=[aid], days=28)
        c = sum(ch.values()); total += c; ok += 1
        if (i+1) % 25 == 0:
            print(f"[changes] {i+1}/{len(ids)} ({total} rows, {time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"[changes] {i+1}/{len(ids)} {aid}: ERROR {e}", flush=True)
print(f"[changes] done: {total} rows across {ok} accounts ({time.time()-t0:.0f}s)", flush=True)
print("change_events total:", db.fetchone("SELECT count(*) FROM change_events")[0], flush=True)
print("change_timestamp range:", db.fetchone("SELECT min(change_timestamp), max(change_timestamp) FROM change_events"), flush=True)
print("[changes] DONE", flush=True)
db.close()
