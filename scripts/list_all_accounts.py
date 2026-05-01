"""Pull 30-day spend summary for all accounts from the MCC."""

import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from brightmatter.storage.database import Database
from brightmatter.ingestion.client import GoogleAdsClient
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

db = Database()
db.initialize()

rows = db.fetchall("SELECT account_id, account_name FROM accounts ORDER BY account_name")
console = Console()
console.print(f"\nQuerying {len(rows)} accounts for 30-day summary...\n")

client = GoogleAdsClient()

QUERY = """
SELECT
  metrics.cost_micros,
  metrics.impressions,
  metrics.clicks,
  metrics.conversions,
  metrics.conversions_value
FROM customer
WHERE segments.date DURING LAST_30_DAYS
"""

results = []
errors = 0

with Progress(console=console) as progress:
    task = progress.add_task("Pulling account summaries...", total=len(rows))
    for acct_id, acct_name in rows:
        try:
            api_rows = client.query(acct_id, QUERY)
            if api_rows:
                m = api_rows[0].metrics
                cost = m.cost_micros / 1_000_000
                results.append({
                    "id": acct_id, "name": acct_name,
                    "cost": cost, "impressions": m.impressions,
                    "clicks": m.clicks, "conversions": m.conversions,
                    "conv_value": m.conversions_value,
                })
            else:
                results.append({"id": acct_id, "name": acct_name,
                               "cost": 0, "impressions": 0, "clicks": 0,
                               "conversions": 0, "conv_value": 0})
        except Exception:
            results.append({"id": acct_id, "name": acct_name,
                           "cost": -1, "impressions": 0, "clicks": 0,
                           "conversions": 0, "conv_value": 0})
            errors += 1
        progress.update(task, advance=1)

results.sort(key=lambda r: r["cost"], reverse=True)

table = Table(title=f"All {len(results)} Accounts — Last 30 Days (errors: {errors})")
table.add_column("#", style="dim", width=4)
table.add_column("Account ID", style="cyan", width=12)
table.add_column("Name", width=30)
table.add_column("Spend", justify="right", width=12)
table.add_column("Impressions", justify="right", width=14)
table.add_column("Clicks", justify="right", width=10)
table.add_column("Conversions", justify="right", width=12)
table.add_column("Conv Value", justify="right", width=12)
table.add_column("Status", width=10)

active_count = 0
for i, r in enumerate(results, 1):
    if r["cost"] < 0:
        status = "[red]error[/red]"
    elif r["cost"] == 0 and r["impressions"] == 0:
        status = "[dim]inactive[/dim]"
    elif r["cost"] < 100:
        status = "[yellow]low[/yellow]"
    else:
        status = "[green]active[/green]"
        active_count += 1

    cost_str = f"${r['cost']:,.0f}" if r["cost"] >= 0 else "—"
    impr_str = f"{r['impressions']:,}" if r["impressions"] else "0"
    click_str = f"{r['clicks']:,}" if r["clicks"] else "0"
    conv_str = f"{r['conversions']:,.1f}" if r["conversions"] else "0"
    val_str = f"${r['conv_value']:,.0f}" if r["conv_value"] else "$0"

    table.add_row(str(i), r["id"], r["name"][:30], cost_str, impr_str,
                  click_str, conv_str, val_str, status)

console.print(table)

total_spend = sum(r["cost"] for r in results if r["cost"] > 0)
total_conv = sum(r["conversions"] for r in results if r["conversions"] > 0)
total_value = sum(r["conv_value"] for r in results if r["conv_value"] > 0)
console.print(f"\n[bold]Summary:[/bold] {active_count} active accounts (>$100 spend)")
console.print(f"Total 30-day spend: ${total_spend:,.0f}")
console.print(f"Total conversions: {total_conv:,.0f}")
console.print(f"Total conversion value: ${total_value:,.0f}\n")

db.close()
