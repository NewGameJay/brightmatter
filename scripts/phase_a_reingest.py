"""Phase A: re-ingest the existing accounts with the budget + search-terms fixes.

Pulls a 60-day daily window (so every detector window has real
daily_budget_micros) plus 30-day search-term performance, then re-classifies.
Targets only the accounts that already have daily_metrics.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

db = Database()
db.initialize()
repo = Repository(db)
pipe = IngestionPipeline(repo)

ids = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]
print(f"[phase-a] re-ingesting {len(ids)} existing accounts", flush=True)

daily = pipe.ingest_daily(account_ids=ids, days=60)
print(f"[phase-a] daily rows: {sum(daily.values())} across {len(daily)} accounts", flush=True)

st = pipe.ingest_search_terms(account_ids=ids, days=30)
print(f"[phase-a] search-term rows: {sum(st.values())} across {len(st)} accounts", flush=True)

n = pipe.classify_accounts()
print(f"[phase-a] re-classified: {n}", flush=True)

# Sanity: how much budget data did we get, and how many search terms?
bud = db.fetchone(
    "SELECT count(*), count(CASE WHEN daily_budget_micros>0 THEN 1 END) FROM daily_metrics WHERE date >= current_date - 60"
)
print(f"[phase-a] daily_metrics last 60d: {bud[0]} rows, {bud[1]} with budget>0", flush=True)
print(f"[phase-a] search_terms total rows: {db.fetchone('SELECT count(*) FROM search_terms')[0]}", flush=True)
print("[phase-a] DONE", flush=True)
db.close()
