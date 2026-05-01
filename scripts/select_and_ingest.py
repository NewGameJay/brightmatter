"""Select accounts #6-25 by spend + Binance.US, ingest data, and run analysis."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from rich.table import Table
from rich.progress import Progress

from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository
from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.analysis.engine import AnalysisEngine

console = Console()

# ── Step 1: Rank all accounts by 30-day spend ──

db = Database()
db.initialize()
repo = Repository(db)

rows = db.fetchall("SELECT account_id, account_name FROM accounts ORDER BY account_name")
client = GoogleAdsClient()

console.print(f"\n[bold]Step 1:[/bold] Ranking {len(rows)} accounts by 30-day spend...\n")

QUERY = "SELECT metrics.cost_micros FROM customer WHERE segments.date DURING LAST_30_DAYS"
spend = []

with Progress(console=console) as progress:
    task = progress.add_task("Ranking by spend...", total=len(rows))
    for aid, name in rows:
        try:
            r = client.query(aid, QUERY)
            cost = r[0].metrics.cost_micros / 1e6 if r else 0
            spend.append((aid, name, cost))
        except Exception:
            spend.append((aid, name, -1))
        progress.update(task, advance=1)

spend.sort(key=lambda x: x[2], reverse=True)

# Show top 30 for reference
table = Table(title="Top 30 by Spend")
table.add_column("#", width=4)
table.add_column("ID", style="cyan")
table.add_column("Name", width=30)
table.add_column("30d Spend", justify="right")
table.add_column("Selected")

binance = [x for x in spend if "binance" in x[1].lower()]
binance_id = binance[0][0] if binance else None
binance_rank = spend.index(binance[0]) + 1 if binance else 0

# Build selection: ranks 6-25
selected_ids = [s[0] for s in spend[5:25]]

# Add Binance if not already in selection
if binance_id and binance_id not in selected_ids:
    selected_ids.append(binance_id)
elif binance_id and binance_id in selected_ids:
    selected_ids.append(spend[25][0])

for i, (aid, name, cost) in enumerate(spend[:30], 1):
    marker = ""
    if 6 <= i <= 25:
        marker = "[green]YES[/green]"
    elif aid == binance_id:
        marker = "[green]YES (Binance)[/green]"
    elif i <= 5:
        marker = "[dim]skip (top 5)[/dim]"
    table.add_row(str(i), aid, name[:30], f"${cost:,.0f}", marker)

console.print(table)
console.print(f"\nBinance.US: rank #{binance_rank} (ID: {binance_id})")
console.print(f"[bold]Selected {len(selected_ids)} accounts for ingestion[/bold]\n")

# ── Step 2: Ingest data for selected accounts ──

console.print("[bold]Step 2:[/bold] Ingesting 30 days of data for selected accounts...\n")

pipeline = IngestionPipeline(repo)

console.print("  Pulling daily campaign metrics (30 days)...")
daily = pipeline.ingest_daily(account_ids=selected_ids, days=30)
console.print(f"  [green]Done:[/green] {sum(daily.values())} daily metric rows across {len(daily)} accounts\n")

console.print("  Pulling keyword Quality Score data (7 days)...")
kw = pipeline.ingest_keywords(account_ids=selected_ids, days=7)
console.print(f"  [green]Done:[/green] {sum(kw.values())} keyword rows\n")

console.print("  Pulling change history (90 days)...")
ch = pipeline.ingest_changes(account_ids=selected_ids, days=90)
console.print(f"  [green]Done:[/green] {sum(ch.values())} change events\n")

# ── Step 3: Run analysis ──

console.print("[bold]Step 3:[/bold] Running analysis...\n")

engine = AnalysisEngine(db, repo)
signals = engine.run_detectors_only()

console.print(f"  [green]Detectors found {len(signals)} signals[/green]\n")

# Show signals
if signals:
    sig_table = Table(title=f"Detected Signals ({len(signals)})")
    sig_table.add_column("Sev", width=8)
    sig_table.add_column("Account ID", style="cyan", width=12)
    sig_table.add_column("Account", width=25)
    sig_table.add_column("Domain", width=20)
    sig_table.add_column("Type", width=25)
    sig_table.add_column("Message", width=60)

    sev_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}
    for s in sorted(signals, key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x.severity.value, 3)):
        acct = next((n for a, n, c in spend if a == s.account_id), s.account_id)
        sig_table.add_row(
            f"[{sev_style.get(s.severity.value, '')}]{s.severity.value}[/]",
            s.account_id, acct[:25], s.domain.value, s.signal_type,
            s.message[:60],
        )
    console.print(sig_table)

# Show patterns
patterns_data = repo.get_patterns()
if patterns_data and patterns_data.get("pattern_id"):
    console.print()
    pat_table = Table(title="Patterns")
    pat_table.add_column("Domain", width=20)
    pat_table.add_column("Type", width=15)
    pat_table.add_column("Sev", width=8)
    pat_table.add_column("Confidence", width=10)
    pat_table.add_column("Summary", width=80)
    for i in range(len(patterns_data["pattern_id"])):
        pat_table.add_row(
            patterns_data["domain"][i],
            patterns_data["pattern_type"][i],
            patterns_data["severity"][i],
            f"{patterns_data['confidence'][i]:.0%}",
            patterns_data["summary"][i][:80] if patterns_data["summary"][i] else "",
        )
    console.print(pat_table)

# Status
console.print()
from brightmatter.cli import cmd_status
import argparse
cmd_status(argparse.Namespace(verbose=False))

db.close()
