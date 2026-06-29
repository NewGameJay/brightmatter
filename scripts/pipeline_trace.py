"""Emit the 6-stage pipeline trace for a campaign (feeds the BrightMatter Pipeline UI).

Usage:
  python scripts/pipeline_trace.py <account_id> <campaign_id>   # one campaign -> JSON
  python scripts/pipeline_trace.py --top 5                      # richest-episode campaigns
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.observability.trace import build_pipeline_trace

db = Database(); db.initialize()

if "--top" in sys.argv:
    k = int(sys.argv[sys.argv.index("--top") + 1])
    camps = db.fetchall("""SELECT e.account_id, e.campaign_id, count(*) n
                           FROM episodes e WHERE e.campaign_id<>'' GROUP BY 1,2 ORDER BY n DESC LIMIT ?""", [k])
    traces = [build_pipeline_trace(db, a, c) for a, c, _ in camps]
    out = Path(__file__).resolve().parent.parent / "docs" / "pipeline-traces.json"
    out.write_text(json.dumps(traces, indent=2, default=str))
    print(f"{len(traces)} traces -> {out}")
    for t in traces:
        a = t.get("analysis", {}); r = t.get("recommendation", {}); m = t.get("monitoring", {})
        print(f"  {t['account'][:24]:24} {t['campaign_id']:14} state={a.get('state')} "
              f"-> {r.get('call')} | resolved={m.get('resolved')}")
else:
    acct, camp = sys.argv[1], sys.argv[2]
    t = build_pipeline_trace(db, acct, camp)
    print(json.dumps(t, indent=2, default=str))
db.close()
