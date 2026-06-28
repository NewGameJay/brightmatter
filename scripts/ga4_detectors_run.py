"""Run GA4 detectors (Domains 1-2) on ingested ga4_landing_pages; persist signals."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.analysis.ga4_detectors import run_ga4_detectors

db = Database(); db.initialize(); repo = Repository(db)
GA4_TYPES = ("ga4_engagement_drop", "ga4_session_duration_collapse",
             "ga4_mobile_engagement_gap", "ga4_mobile_bounce_regression",
             "ga4_paid_organic_gap", "ga4_funnel_dropoff")
db.execute("DELETE FROM signals WHERE signal_type IN " + str(GA4_TYPES))

sigs = run_ga4_detectors(db)
for s in sigs:
    repo.insert_signal(s)
db.execute("CHECKPOINT")

print(f"[ga4-det] signals: {len(sigs)} across {len(set(s.account_id for s in sigs))} accounts")
print(f"[ga4-det] by type: {dict(Counter(s.signal_type for s in sigs))}")
print(f"[ga4-det] by severity: {dict(Counter(s.severity.value for s in sigs))}")
print("\n[ga4-det] top signals (worst first):")
for s in sorted(sigs, key=lambda s: -abs(s.value - s.threshold))[:12]:
    print(f"   [{s.signal_type:30}] {s.message[:110]}")
db.close()
print("\n[ga4-det] DONE")
