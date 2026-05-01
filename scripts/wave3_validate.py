"""Wave 3: Ingest assets + classify, run all 21 detectors, final scorecard."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.analysis import detectors as det

console = Console()
db = Database(); db.initialize()
repo = Repository(db)
pipeline = IngestionPipeline(repo)

selected_ids = [r[0] for r in db.fetchall("SELECT DISTINCT account_id FROM daily_metrics")]

# ── Ingest assets ──
console.print(f"\n[bold]Wave 3:[/bold] Ingesting assets for {len(selected_ids)} accounts...")
asset_results = pipeline.ingest_assets(account_ids=selected_ids)
total_assets = sum(asset_results.values())
console.print(f"  Assets: {total_assets} rows from {sum(1 for v in asset_results.values() if v > 0)} accounts")

# ── Classify accounts ──
console.print("  Classifying accounts...")
classified = pipeline.classify_accounts()
console.print(f"  Classified: {classified} accounts\n")

# Show classifications
accts = repo.list_accounts()
classified_list = [(a.account_id, a.account_name, a.business_type.value, a.vertical) 
                   for a in accts if a.business_type.value != "unknown" and a.account_id in selected_ids]
if classified_list:
    ct = Table(title="Account Classifications")
    ct.add_column("ID", style="cyan")
    ct.add_column("Name", width=25)
    ct.add_column("Type")
    ct.add_column("Vertical")
    for aid, name, btype, vert in sorted(classified_list, key=lambda x: x[1]):
        ct.add_row(aid, name[:25], btype, vert)
    console.print(ct)

# ── Run all detectors ──
console.print("\n[bold]Running all 21 detectors...[/bold]\n")

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
    ("W3", "missing_extensions", det.detect_missing_extensions),
    ("W3", "cross_account_outlier", det.detect_cross_account_outlier),
    ("W3", "pmax_low_conv_volume", det.detect_pmax_low_conversion_volume),
]

total = 0
credible = 0
silent = 0
noisy = 0
errors = 0

table = Table(title="FINAL SCORECARD: All 21 Detectors")
table.add_column("Wave", width=4)
table.add_column("Detector", width=32)
table.add_column("Signals", justify="right", width=8)
table.add_column("Accounts", justify="right", width=8)
table.add_column("Status", width=10)
table.add_column("Sample", width=55)

for wave, name, fn in all_detectors:
    try:
        s = fn(db)
        accts = len(set(x.account_id for x in s))
        total += len(s)
        if len(s) > 50:
            status = "[yellow]NOISY[/yellow]"
            noisy += 1
        elif len(s) > 0:
            status = "[green]CREDIBLE[/green]"
            credible += 1
        else:
            status = "[dim]SILENT[/dim]"
            silent += 1
        sample = s[0].message[:55] if s else "[dim]—[/dim]"
        table.add_row(wave, name, str(len(s)), str(accts), status, sample)
    except Exception as e:
        errors += 1
        table.add_row(wave, name, "—", "—", "[red]ERROR[/red]", str(e)[:55])

console.print(table)

console.print(Panel(
    f"Total signals: {total}\n"
    f"CREDIBLE: {credible}/21\n"
    f"SILENT:   {silent}/21 (pattern not present in 21 accounts)\n"
    f"NOISY:    {noisy}/21\n"
    f"ERRORS:   {errors}/21",
    title="Final Summary",
))

# Data totals
console.print("\n[bold]Data Inventory:[/bold]")
tables_to_check = [
    "daily_metrics", "keyword_metrics", "change_events",
    "conversion_actions", "keyword_counts", "asset_coverage",
]
for t in tables_to_check:
    try:
        row = db.fetchone(f"SELECT count(*), count(DISTINCT account_id) FROM {t}")
        console.print(f"  {t}: {row[0]:,} rows, {row[1]} accounts")
    except Exception:
        console.print(f"  {t}: [red]table not found[/red]")

db.close()
