"""Phase B (resume): ingest the 150 already-ranked accounts.

The ranking pass already picked the top-150-by-spend ids (saved to
/tmp/phase_b_ids.txt); this skips re-ranking and just ingests daily (60d,
with budget), search terms (30d), and changes (90d) for each. The accounts
table NULL-string rows have been repaired, so list_accounts() works.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

ids = [l.strip() for l in open("/tmp/phase_b_ids.txt") if l.strip()]
print(f"[phase-b-resume] ingesting {len(ids)} accounts", flush=True)

db = Database()
db.initialize()
repo = Repository(db)
pipe = IngestionPipeline(repo)

t0 = time.time()
ok = 0
for i, aid in enumerate(ids):
    try:
        d = pipe.ingest_daily(account_ids=[aid], days=60)
        st = pipe.ingest_search_terms(account_ids=[aid], days=30)
        ch = pipe.ingest_changes(account_ids=[aid], days=90)
        ok += 1
        print(f"[phase-b-resume] {i + 1}/{len(ids)} {aid}: "
              f"daily={sum(d.values())} terms={sum(st.values())} "
              f"changes={sum(ch.values())} ({time.time() - t0:.0f}s)", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[phase-b-resume] {i + 1}/{len(ids)} {aid}: ERROR {e}", flush=True)

n = pipe.classify_accounts()
print(f"[phase-b-resume] classified: {n}", flush=True)
covered = db.fetchone("SELECT count(DISTINCT account_id) FROM daily_metrics")[0]
st_rows, st_accts = db.fetchone("SELECT count(*), count(DISTINCT account_id) FROM search_terms")
print(f"[phase-b-resume] accounts with daily_metrics: {covered} | "
      f"search_terms: {st_rows} rows / {st_accts} accounts | "
      f"ok={ok}/{len(ids)}", flush=True)
print("[phase-b-resume] DONE", flush=True)
db.close()
