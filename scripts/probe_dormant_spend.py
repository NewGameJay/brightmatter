"""Probe the 217 currently-dormant accounts (0 spend in last 30d) for monthly
spend over the last ~6 months. Reads the dormant ids from the cached ranking
(/tmp/phase3_spend.tsv) so it touches NO DuckDB — safe to run while the
expansion holds the DB write lock. Writes per-account recency to
/tmp/phase3_dormant_6mo.tsv and prints a recency distribution.
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.ingestion.client import GoogleAdsClient

dormant = []
for line in Path("/tmp/phase3_spend.tsv").read_text().splitlines():
    aid, name, cost = line.split("\t")
    if int(cost) <= 0:
        dormant.append((aid, name))
print(f"[probe] {len(dormant)} dormant accounts to check for 6-month history", flush=True)

client = GoogleAdsClient()
# Monthly cost over the last ~6 months. No LAST_180_DAYS literal exists, so use
# an explicit date range. segments.month buckets by calendar month.
from datetime import date, timedelta
_end = date.today()
_start = _end - timedelta(days=183)
Q = ("SELECT segments.month, metrics.cost_micros FROM customer "
     f"WHERE segments.date BETWEEN '{_start.isoformat()}' AND '{_end.isoformat()}'")

out = Path("/tmp/phase3_dormant_6mo.tsv").open("w")
recency = Counter()      # most-recent month with spend (or 'none')
recoverable = 0
total_hist_spend = 0
for i, (aid, name) in enumerate(dormant):
    months = {}  # month -> cost_micros
    try:
        for r in client.query(aid, Q):
            m = str(r.segments.month)
            months[m] = months.get(m, 0) + int(r.metrics.cost_micros)
    except Exception as e:  # noqa: BLE001
        out.write(f"{aid}\t{name}\tERROR\t{e}\n")
        recency["error"] += 1
        continue
    spent_months = sorted(m for m, c in months.items() if c > 0)
    last = spent_months[-1] if spent_months else "none"
    hist = sum(c for c in months.values())
    total_hist_spend += hist
    if spent_months:
        recoverable += 1
        recency[last] += 1
    else:
        recency["none"] += 1
    out.write(f"{aid}\t{name}\t{last}\t{hist/1e6:.0f}\t{','.join(spent_months)}\n")
    if (i + 1) % 50 == 0:
        print(f"[probe] checked {i+1}/{len(dormant)} (recoverable so far={recoverable})", flush=True)
out.close()

print(f"\n[probe] === RESULTS ===", flush=True)
print(f"[probe] dormant accounts checked: {len(dormant)}", flush=True)
print(f"[probe] had ANY spend in last 6mo (recoverable): {recoverable}", flush=True)
print(f"[probe] no spend in last 6mo: {recency.get('none',0)} | errors: {recency.get('error',0)}", flush=True)
print(f"[probe] total historical spend across recoverable: ${total_hist_spend/1e6:,.0f}", flush=True)
print(f"[probe] most-recent-spend-month distribution:", flush=True)
for month, n in sorted(recency.items(), reverse=True):
    if month in ("none", "error"):
        continue
    print(f"[probe]   {month}: {n} accounts", flush=True)
print(f"[probe] detail → /tmp/phase3_dormant_6mo.tsv", flush=True)
