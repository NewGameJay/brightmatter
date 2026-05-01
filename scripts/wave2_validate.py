"""Wave 2: Ingest keyword counts, run all 18 detectors, produce scorecard."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.analysis.detectors import run_all_detectors
# Import individual detectors for the scorecard
from brightmatter.analysis import detectors as det

console = Console()
db = Database(); db.initialize()
repo = Repository(db)
pipeline = IngestionPipeline(repo)

selected_ids = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]
console.print(f"\n[bold]Wave 2:[/bold] Ingesting keyword counts for {len(selected_ids)} accounts...\n")

kc_results = pipeline.ingest_keyword_counts(account_ids=selected_ids)
total_kc = sum(kc_results.values())
success_kc = sum(1 for v in kc_results.values() if v > 0)
console.print(f"  Keyword counts: {total_kc} campaign rows across {success_kc} accounts\n")

console.print("[bold]Running all 18 detectors...[/bold]\n")

all_detectors = [
    ("W0", "tracking_breaks", det.detect_tracking_breaks),
    ("W0", "low_quality_scores", det.detect_low_quality_scores),
    ("W0", "cpa_spikes", det.detect_cpa_spikes),
    ("W0", "impression_share_loss", det.detect_impression_share_loss),
    ("W0", "cvr_anomalies", det.detect_cvr_anomalies),
    ("W0", "brand_nonbrand_contamination", det.detect_brand_nonbrand_contamination),
    ("W0", "pmax_channel_imbalance", det.detect_pmax_channel_imbalance),
    ("W0", "auto_applied_changes", det.detect_auto_applied_changes),
    ("W0", "budget_capped", det.detect_budget_capped_campaigns),
    ("W0", "bidding_antipatterns", det.detect_bidding_antipatterns),
    ("W1", "suspicious_primary_conv", det.detect_suspicious_primary_conversions),
    ("W1", "duplicate_primary_conv", det.detect_duplicate_primary_conversions),
    ("W1", "missing_conversion_value", det.detect_missing_conversion_value),
    ("W1", "over_segmentation", det.detect_over_segmentation),
    ("W2", "missing_brand_separation", det.detect_missing_brand_separation),
    ("W2", "campaign_type_gaps", det.detect_campaign_type_gaps),
    ("W2", "broad_without_smart_bidding", det.detect_broad_without_smart_bidding),
    ("W2", "low_negative_ratio", det.detect_low_negative_ratio),
]

total = 0
credible = 0
for wave, name, fn in all_detectors:
    try:
        s = fn(db)
        accts = len(set(x.account_id for x in s))
        total += len(s)
        status = "CREDIBLE" if 0 < len(s) <= 50 else ("NOISY" if len(s) > 50 else "SILENT")
        if status == "CREDIBLE":
            credible += 1
        sample = s[0].message[:70] if s else ""
        print(f"  {wave} {name:35s} | {len(s):>4} sig | {accts:>2} accts | {status:8s} | {sample}")
    except Exception as e:
        print(f"  {wave} {name:35s} | ERROR: {str(e)[:80]}")

console.print(f"\n[bold]Total: {total} signals, {credible}/18 CREDIBLE[/bold]")

for label, query in [
    ("daily_metrics", "SELECT count(*), count(DISTINCT account_id) FROM daily_metrics"),
    ("keyword_metrics", "SELECT count(*), count(DISTINCT account_id) FROM keyword_metrics"),
    ("change_events", "SELECT count(*), count(DISTINCT account_id) FROM change_events"),
    ("conversion_actions", "SELECT count(*), count(DISTINCT account_id) FROM conversion_actions"),
    ("keyword_counts", "SELECT count(*), count(DISTINCT account_id) FROM keyword_counts"),
]:
    row = db.fetchone(query)
    console.print(f"  {label}: {row[0]:,} rows, {row[1]} accounts")

db.close()
