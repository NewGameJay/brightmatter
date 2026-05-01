"""Wave 1: Ingest conversion actions, run all 14 detectors, produce scorecard."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.analysis.detectors import (
    detect_tracking_breaks, detect_low_quality_scores, detect_cpa_spikes,
    detect_impression_share_loss, detect_cvr_anomalies,
    detect_brand_nonbrand_contamination, detect_pmax_channel_imbalance,
    detect_auto_applied_changes, detect_budget_capped_campaigns,
    detect_bidding_antipatterns,
    detect_suspicious_primary_conversions, detect_duplicate_primary_conversions,
    detect_missing_conversion_value, detect_over_segmentation,
)

console = Console()
db = Database(); db.initialize()
repo = Repository(db)
pipeline = IngestionPipeline(repo)

selected_ids = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]
console.print(f"\n[bold]Wave 1:[/bold] Ingesting conversion actions for {len(selected_ids)} accounts...\n")

ca_results = pipeline.ingest_conversion_actions(account_ids=selected_ids)
total_ca = sum(ca_results.values())
success_ca = sum(1 for v in ca_results.values() if v > 0)
console.print(f"  Conversion actions: {total_ca} across {success_ca} accounts\n")

console.print("[bold]Running all 14 detectors...[/bold]\n")

detectors = [
    ("tracking_breaks", detect_tracking_breaks),
    ("low_quality_scores", detect_low_quality_scores),
    ("cpa_spikes", detect_cpa_spikes),
    ("impression_share_loss", detect_impression_share_loss),
    ("cvr_anomalies", detect_cvr_anomalies),
    ("brand_nonbrand_contamination", detect_brand_nonbrand_contamination),
    ("pmax_channel_imbalance", detect_pmax_channel_imbalance),
    ("auto_applied_changes", detect_auto_applied_changes),
    ("budget_capped", detect_budget_capped_campaigns),
    ("bidding_antipatterns", detect_bidding_antipatterns),
    ("suspicious_primary_conv", detect_suspicious_primary_conversions),
    ("duplicate_primary_conv", detect_duplicate_primary_conversions),
    ("missing_conversion_value", detect_missing_conversion_value),
    ("over_segmentation", detect_over_segmentation),
]

total = 0
for name, fn in detectors:
    try:
        s = fn(db)
        accts = len(set(x.account_id for x in s))
        total += len(s)
        wave = "W0" if detectors.index((name, fn)) < 10 else "W1"
        status = "CREDIBLE" if 0 < len(s) <= 50 else ("NOISY" if len(s) > 50 else "SILENT")
        sample = s[0].message[:70] if s else ""
        print(f"  {wave} {name:35s} | {len(s):>4} sig | {accts:>2} accts | {status:8s} | {sample}")
    except Exception as e:
        print(f"  {name:35s} | ERROR: {str(e)[:80]}")

console.print(f"\n[bold]Total: {total} signals across 14 detectors[/bold]")

# Data check
for label, query in [
    ("daily_metrics", "SELECT count(*), count(DISTINCT account_id) FROM daily_metrics"),
    ("keyword_metrics", "SELECT count(*), count(DISTINCT account_id) FROM keyword_metrics"),
    ("change_events", "SELECT count(*), count(DISTINCT account_id) FROM change_events"),
    ("conversion_actions", "SELECT count(*), count(DISTINCT account_id) FROM conversion_actions"),
]:
    row = db.fetchone(query)
    console.print(f"  {label}: {row[0]:,} rows, {row[1]} accounts")

db.close()
