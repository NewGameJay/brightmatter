"""Ingest ranks 26-50 by 30-day spend with the same data shape as ranks 6-25.

READ-ONLY: this script ONLY pulls data from Google Ads (GAQL SELECT via
SearchStream). The GoogleAdsClient hard-blocks every mutate path. All writes
in this script are to the local DuckDB; nothing touches the live accounts.

Data pulled per account:
  - 30 days of daily campaign metrics
  - 7 days of keyword Quality Score / match-type data
  - 90 days of change history
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from brightmatter.ingestion.client import GoogleAdsClient
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

console = Console()

RANK_START = 26  # 1-indexed
RANK_END = 50

SPEND_QUERY = "SELECT metrics.cost_micros FROM customer WHERE segments.date DURING LAST_30_DAYS"


def main():
    db = Database()
    db.initialize()
    repo = Repository(db)

    rows = db.fetchall("SELECT account_id, account_name FROM accounts ORDER BY account_name")
    console.print(f"\n[bold]Ranking {len(rows)} accounts by 30-day spend...[/bold]")
    console.print("[dim]Read-only: GAQL SELECT only; no writes to Google Ads.[/dim]\n")

    client = GoogleAdsClient()
    spend: list[tuple[str, str, float]] = []
    errors = 0

    with Progress(console=console) as progress:
        task = progress.add_task("Ranking by spend...", total=len(rows))
        for aid, name in rows:
            try:
                r = client.query(aid, SPEND_QUERY)
                cost = r[0].metrics.cost_micros / 1e6 if r else 0.0
                spend.append((aid, name, cost))
            except Exception:
                errors += 1
                spend.append((aid, name, -1.0))
            progress.update(task, advance=1)

    spend.sort(key=lambda x: x[2], reverse=True)

    # Skip accounts that already have ingested daily metrics so we don't
    # re-pull the same ranks. The previous run grabbed ranks 6-25.
    already_ingested = {
        r[0] for r in db.fetchall(
            "SELECT DISTINCT account_id FROM daily_metrics"
        )
    }

    window = spend[RANK_START - 1:RANK_END]
    selection = [e for e in window if e[0] not in already_ingested]

    table = Table(title=f"Selected ranks {RANK_START}-{RANK_END} (excluding already-ingested)")
    table.add_column("Rank", justify="right", width=6)
    table.add_column("ID", style="cyan", width=12)
    table.add_column("Name", width=40)
    table.add_column("30d Spend", justify="right", width=14)
    table.add_column("Status")
    for i, entry in enumerate(window, start=RANK_START):
        marker = "[dim]already ingested[/]" if entry[0] in already_ingested else "[green]selected[/]"
        table.add_row(str(i), entry[0], (entry[1] or "")[:40], f"${entry[2]:,.0f}", marker)
    console.print(table)
    console.print(f"\nWill ingest [bold]{len(selection)}[/] account(s). Ranking errors: {errors}.\n")

    if not selection:
        console.print("[yellow]Nothing to ingest.[/yellow]")
        db.close()
        return

    selected_ids = [s[0] for s in selection]
    pipeline = IngestionPipeline(repo)

    console.print("[bold]Step 1:[/bold] Daily campaign metrics (30 days)...")
    daily = pipeline.ingest_daily(account_ids=selected_ids, days=30)
    console.print(f"  {sum(daily.values())} rows across {len(daily)} accounts.\n")

    console.print("[bold]Step 2:[/bold] Keyword Quality Score data (7 days)...")
    kw = pipeline.ingest_keywords(account_ids=selected_ids, days=7)
    console.print(f"  {sum(kw.values())} rows.\n")

    console.print("[bold]Step 3:[/bold] Change history (90 days)...")
    ch = pipeline.ingest_changes(account_ids=selected_ids, days=90)
    console.print(f"  {sum(ch.values())} change events.\n")

    console.print("[green]Ingestion complete (read-only).[/green]")
    db.close()


if __name__ == "__main__":
    main()
