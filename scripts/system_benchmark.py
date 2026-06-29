"""Benchmark the full BrightMatter system — one scorecard across every layer.

Usage: python scripts/system_benchmark.py [--harnesses] [--json]
  --harnesses  also sweep all detector harnesses (slower)
  --json       emit the scorecard as JSON (for dashboards)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.observability.benchmark import system_scorecard, print_scorecard

db = Database(); db.initialize()
sc = system_scorecard(db, run_harnesses="--harnesses" in sys.argv)
if "--json" in sys.argv:
    out = Path(__file__).resolve().parent.parent / "docs" / "system-scorecard.json"
    out.write_text(json.dumps(sc, indent=2, default=str))
    print(f"scorecard JSON -> {out}")
else:
    print_scorecard(sc)
db.close()
