"""Wave 0: Fix broken data, re-ingest, validate all 10 detectors."""

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
from brightmatter.analysis.detectors import (
    detect_tracking_breaks, detect_low_quality_scores, detect_cpa_spikes,
    detect_impression_share_loss, detect_cvr_anomalies,
    detect_brand_nonbrand_contamination, detect_pmax_channel_imbalance,
    detect_auto_applied_changes, detect_budget_capped_campaigns,
    detect_bidding_antipatterns,
)

console = Console()

db = Database()
db.initialize()
repo = Repository(db)
pipeline = IngestionPipeline(repo)

# Get the 21 selected accounts
accounts = repo.list_accounts()
# Filter to accounts that have daily_metrics (the ones we already ingested)
accts_with_data = db.fetchall(
    "SELECT DISTINCT account_id FROM daily_metrics"
)
selected_ids = [r[0] for r in accts_with_data]
console.print(f"\n[bold]Wave 0:[/bold] Re-ingesting fixed data for {len(selected_ids)} accounts\n")

# ── Step 1: Re-ingest keyword data with fixed QS query ──
console.print("[bold]Step 1a:[/bold] Re-ingesting keyword QS data (fixed query)...")
kw_results = pipeline.ingest_keywords(account_ids=selected_ids, days=7)
total_kw = sum(kw_results.values())
success_kw = sum(1 for v in kw_results.values() if v > 0)
fail_kw = sum(1 for v in kw_results.values() if v == 0)
console.print(f"  Keywords: {total_kw} rows from {success_kw} accounts ({fail_kw} returned 0)\n")

# ── Step 2: Re-ingest change events ──
console.print("[bold]Step 1b:[/bold] Re-ingesting change events (90 days)...")
ch_results = pipeline.ingest_changes(account_ids=selected_ids, days=90)
total_ch = sum(ch_results.values())
success_ch = sum(1 for v in ch_results.values() if v > 0)
console.print(f"  Changes: {total_ch} events from {success_ch} accounts\n")

# Show per-account breakdown for change events
if total_ch == 0:
    console.print("  [yellow]Zero change events — checking individual accounts...[/yellow]")
    for aid in selected_ids[:3]:
        acct = repo.get_account(aid)
        name = acct.account_name if acct else aid
        count = ch_results.get(aid, 0)
        console.print(f"    {aid} ({name}): {count} events")

# ── Step 3: Run all 10 detectors individually ──
console.print("\n[bold]Step 2:[/bold] Running all 10 detectors individually...\n")

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
]

scorecard = []
all_signals = []

for name, fn in detectors:
    try:
        signals = fn(db)
        accounts_hit = list({s.account_id for s in signals})
        severities = {}
        for s in signals:
            severities[s.severity.value] = severities.get(s.severity.value, 0) + 1
        scorecard.append({
            "name": name,
            "fires": len(signals) > 0,
            "count": len(signals),
            "accounts": len(accounts_hit),
            "account_list": accounts_hit[:5],
            "severities": severities,
            "error": None,
            "sample": signals[0].message[:80] if signals else "",
        })
        all_signals.extend(signals)
    except Exception as e:
        scorecard.append({
            "name": name,
            "fires": False,
            "count": 0,
            "accounts": 0,
            "account_list": [],
            "severities": {},
            "error": str(e)[:100],
            "sample": "",
        })

# ── Step 4: Print scorecard ──
console.print()
table = Table(title="Wave 0: Detector Scorecard (10 Detectors)")
table.add_column("#", width=3)
table.add_column("Detector", width=32)
table.add_column("Fires?", width=6)
table.add_column("Signals", justify="right", width=8)
table.add_column("Accounts", justify="right", width=9)
table.add_column("Severities", width=20)
table.add_column("Sample Signal", width=50)

for i, d in enumerate(scorecard, 1):
    if d["error"]:
        fires = "[red]ERROR[/red]"
        sample = f"[red]{d['error']}[/red]"
    elif d["fires"]:
        fires = "[green]YES[/green]"
        sample = d["sample"]
    else:
        fires = "[dim]NO[/dim]"
        sample = "[dim]no signals[/dim]"

    sev_str = ", ".join(f"{k}:{v}" for k, v in d["severities"].items()) if d["severities"] else "—"

    table.add_row(
        str(i), d["name"], fires, str(d["count"]),
        str(d["accounts"]), sev_str, sample[:50],
    )

console.print(table)

# ── Step 5: Assessment and recommendations ──
console.print()
console.print(Panel(
    f"Total signals: {len(all_signals)}\n"
    f"Detectors firing: {sum(1 for d in scorecard if d['fires'])}/10\n"
    f"Detectors broken: {sum(1 for d in scorecard if d['error'])}/10\n"
    f"Detectors silent: {sum(1 for d in scorecard if not d['fires'] and not d['error'])}/10",
    title="Wave 0 Summary",
))

# Detailed per-detector assessment
console.print("\n[bold]Per-Detector Assessment:[/bold]\n")
for d in scorecard:
    name = d["name"]
    if d["error"]:
        console.print(f"  [red]✗[/red] {name}: ERROR — {d['error']}")
    elif d["count"] > 200:
        console.print(f"  [yellow]![/yellow] {name}: {d['count']} signals across {d['accounts']} accts — TOO NOISY, threshold needs raising")
    elif d["count"] > 50:
        console.print(f"  [yellow]~[/yellow] {name}: {d['count']} signals across {d['accounts']} accts — may be noisy, review samples")
    elif d["count"] > 0:
        console.print(f"  [green]✓[/green] {name}: {d['count']} signals across {d['accounts']} accts — looks credible")
        if d["account_list"]:
            names = []
            for aid in d["account_list"][:3]:
                a = repo.get_account(aid)
                names.append(a.account_name if a else aid)
            console.print(f"      Accounts: {', '.join(names)}")
    else:
        console.print(f"  [dim]—[/dim] {name}: 0 signals — pattern not present or detector not matching")

# Check data availability
console.print("\n[bold]Data Availability:[/bold]")
for label, query in [
    ("daily_metrics", "SELECT count(*), count(DISTINCT account_id) FROM daily_metrics"),
    ("keyword_metrics", "SELECT count(*), count(DISTINCT account_id) FROM keyword_metrics"),
    ("change_events", "SELECT count(*), count(DISTINCT account_id) FROM change_events"),
]:
    row = db.fetchone(query)
    console.print(f"  {label}: {row[0]:,} rows, {row[1]} accounts")

db.close()
