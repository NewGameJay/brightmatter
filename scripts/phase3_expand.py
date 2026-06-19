"""Phase 3.0: expand ingestion to the top ~300 accounts by 30-day spend.

Why re-ingest everyone (not just the new ~150): all three ingest paths are
idempotent — daily_metrics/search_terms are INSERT OR REPLACE, change_events is
INSERT OR IGNORE on a deterministic sha256 change_id — so re-touching the
existing 153 costs nothing but API time and buys a UNIFORM panel: every account
ends on the same date. A ragged right edge (old accounts ending Jun14, new ones
ending Jun18) would manufacture false drop/insufficient signals in the 30-day
windows, which would poison the 2.7 FP measurement and Phase 3 segment stats.

Resumable: ranking is cached to /tmp/phase3_spend.tsv, completed accounts are
appended to /tmp/phase3_done.txt and skipped on restart. Safe to re-run after a
crash (matches the Phase B failure mode).
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

TARGET = 300
DAILY_DAYS = 80      # covers the existing Mar30 span + extends to ~yesterday
TERMS_DAYS = 30
CHANGE_DAYS = 90     # ingest_changes internally caps to 28 (API 30d limit)

SPEND_CACHE = Path("/tmp/phase3_spend.tsv")
DONE_LOG = Path("/tmp/phase3_done.txt")

db = Database()
db.initialize()
repo = Repository(db)
client = GoogleAdsClient()
pipe = IngestionPipeline(repo)

# ── 1. Rank accessible accounts by 30-day spend (cached for resume) ──
if SPEND_CACHE.exists():
    spend = []
    for line in SPEND_CACHE.read_text().splitlines():
        aid, name, cost = line.split("\t")
        spend.append((aid, name, int(cost)))
    print(f"[p3] loaded cached ranking of {len(spend)} accounts", flush=True)
else:
    accts = client.list_accessible_accounts()
    print(f"[p3] ranking {len(accts)} accessible accounts by 30d spend", flush=True)
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
            print(f"[p3] ranked {i + 1}/{len(accts)}", flush=True)
    spend.sort(key=lambda x: x[2], reverse=True)
    SPEND_CACHE.write_text(
        "\n".join(f"{a}\t{n}\t{c}" for a, n, c in spend)
    )
    print(f"[p3] cached ranking → {SPEND_CACHE}", flush=True)

top = [s for s in spend if s[2] > 0][:TARGET]
print(f"[p3] selected top {len(top)} by spend "
      f"(max ${top[0][2] / 1e6:,.0f}/mo, min ${top[-1][2] / 1e6:,.0f}/mo)", flush=True)

# Ensure every selected account exists so _resolve_accounts picks it up.
for aid, name, _ in top:
    repo.db.execute(
        "INSERT OR IGNORE INTO accounts (account_id, account_name) VALUES (?, ?)",
        [aid, name],
    )

# ── 2. Ingest each (daily + search terms + changes), resumable ──
done = set()
if DONE_LOG.exists():
    done = {l.strip() for l in DONE_LOG.read_text().splitlines() if l.strip()}
    print(f"[p3] resuming — {len(done)} accounts already ingested, skipping them", flush=True)

ids = [s[0] for s in top]
t0 = time.time()
ok = len(done)
with DONE_LOG.open("a") as donef:
    for i, aid in enumerate(ids):
        if aid in done:
            continue
        try:
            d = pipe.ingest_daily(account_ids=[aid], days=DAILY_DAYS)
            st = pipe.ingest_search_terms(account_ids=[aid], days=TERMS_DAYS)
            ch = pipe.ingest_changes(account_ids=[aid], days=CHANGE_DAYS)
            ok += 1
            donef.write(aid + "\n"); donef.flush()
            print(f"[p3] {i + 1}/{len(ids)} {aid}: daily={sum(d.values())} "
                  f"terms={sum(st.values())} changes={sum(ch.values())} "
                  f"| ok={ok} ({time.time() - t0:.0f}s)", flush=True)
        except Exception as e:  # noqa: BLE001 — keep going on any single-account failure
            print(f"[p3] {i + 1}/{len(ids)} {aid}: ERROR {e}", flush=True)

# ── 3. Classify (business_type / vertical / spend_tier) ──
n = pipe.classify_accounts()
print(f"[p3] classified: {n}", flush=True)

covered = db.fetchone("SELECT count(DISTINCT account_id) FROM daily_metrics")[0]
dr = db.fetchone("SELECT min(date), max(date) FROM daily_metrics")
rows = db.fetchone("SELECT count(*) FROM daily_metrics")[0]
ce = db.fetchone("SELECT count(*) FROM change_events")[0]
st_rows = db.fetchone("SELECT count(*) FROM search_terms")[0]
db.execute("CHECKPOINT")
print(f"[p3] === COVERAGE === accounts w/ daily={covered} | rows={rows} | "
      f"range={dr[0]}→{dr[1]} | change_events={ce} | search_terms={st_rows} | "
      f"ok={ok}/{len(ids)}", flush=True)
print("[p3] DONE", flush=True)
db.close()
