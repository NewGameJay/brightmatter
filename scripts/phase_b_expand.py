"""Phase B: expand ingestion to 150 accounts, ranked by 30-day spend.

Ranks all MCC-accessible accounts by spend, takes the top 150, and ingests
daily (60d, with budget), search terms (30d), and change history (90d) for
each. Idempotent (INSERT OR REPLACE), per-account logging for monitoring.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

TARGET = 150

db = Database()
db.initialize()
repo = Repository(db)
client = GoogleAdsClient()
pipe = IngestionPipeline(repo)

# 1. Rank accessible accounts by 30-day spend.
accts = client.list_accessible_accounts()
print(f"[phase-b] ranking {len(accts)} accessible accounts by 30d spend", flush=True)
RANK_Q = "SELECT metrics.cost_micros FROM customer WHERE segments.date DURING LAST_30_DAYS"
spend = []
for i, a in enumerate(accts):
    try:
        rows = client.query(a["id"], RANK_Q)
        cost = sum(int(r.metrics.cost_micros) for r in rows)
    except Exception:
        cost = -1
    spend.append((a["id"], a["name"], cost))
    if (i + 1) % 75 == 0:
        print(f"[phase-b] ranked {i + 1}/{len(accts)}", flush=True)
spend.sort(key=lambda x: x[2], reverse=True)
top = [s for s in spend if s[2] > 0][:TARGET]
print(f"[phase-b] selected top {len(top)} by spend "
      f"(max ${top[0][2] / 1e6:,.0f}/mo, min ${top[-1][2] / 1e6:,.0f}/mo)", flush=True)

# Make sure every selected account exists in the accounts table so the
# pipeline's _resolve_accounts will pick it up.
for aid, name, _ in top:
    repo.db.execute(
        "INSERT OR IGNORE INTO accounts (account_id, account_name) VALUES (?, ?)",
        [aid, name],
    )

# 2. Ingest each (daily + search terms + changes), with progress.
ids = [s[0] for s in top]
t0 = time.time()
for i, aid in enumerate(ids):
    try:
        d = pipe.ingest_daily(account_ids=[aid], days=60)
        st = pipe.ingest_search_terms(account_ids=[aid], days=30)
        ch = pipe.ingest_changes(account_ids=[aid], days=90)
        print(f"[phase-b] {i + 1}/{len(ids)} {aid}: "
              f"daily={sum(d.values())} terms={sum(st.values())} "
              f"changes={sum(ch.values())} ({time.time() - t0:.0f}s)", flush=True)
    except Exception as e:  # noqa: BLE001 — keep going on any single-account failure
        print(f"[phase-b] {i + 1}/{len(ids)} {aid}: ERROR {e}", flush=True)

# 3. Classify everything (business_type / vertical / spend_tier).
n = pipe.classify_accounts()
print(f"[phase-b] classified: {n}", flush=True)
covered = db.fetchone("SELECT count(DISTINCT account_id) FROM daily_metrics")[0]
print(f"[phase-b] accounts with daily_metrics: {covered}", flush=True)
print(f"[phase-b] search_terms rows: {db.fetchone('SELECT count(*) FROM search_terms')[0]}", flush=True)
print("[phase-b] DONE", flush=True)
db.close()
