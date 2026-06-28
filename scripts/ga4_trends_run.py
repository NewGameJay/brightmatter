"""Compute GA4 engagement trends per landing page + annotate engagement signals."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.analysis.ga4_trends import compute_engagement_trends, annotate_engagement_signals

db = Database(); db.initialize()
res = compute_engagement_trends(db)
print(f"[ga4-trends] pages with a computed trend: {res['pages_with_trend']}")
print(f"[ga4-trends] distribution: {res['distribution']}")
ann = annotate_engagement_signals(db)
print(f"[ga4-trends] engagement/mobile signals annotated: {ann}")
db.execute("CHECKPOINT")
print("[ga4-trends] DONE")
db.close()
