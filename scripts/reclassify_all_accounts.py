"""Re-classify every account in DuckDB using the new classifier.

For each account we feed account_name + conversion actions + campaign names +
campaign-type counts into brightmatter.ingestion.classifier.classify, then
UPDATE the accounts row. Produces a per-vertical summary table and dumps
the per-account trace for spot-checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from brightmatter.ingestion.classifier import (
    ClassificationInputs,
    classify,
)
from brightmatter.storage.database import Database

console = Console()


def main() -> None:
    db = Database()
    db.initialize()

    accounts = db.fetchall(
        "SELECT account_id, account_name, website_url FROM accounts ORDER BY account_name"
    )
    total = len(accounts)
    console.print(f"\n[bold]Reclassifying {total} accounts...[/bold]\n")

    summary: dict[str, int] = {}
    biz_summary: dict[str, int] = {}
    traces: list[dict] = []
    unknowns: list[tuple[str, str]] = []

    for acct_id, name, website in accounts:
        web_meta = db.fetchone(
            "SELECT title, description FROM account_web_meta WHERE account_id = ?",
            [acct_id],
        )
        title_text = (web_meta[0] if web_meta else "") or ""
        description_text = (web_meta[1] if web_meta else "") or ""

        conv_rows = db.fetchall(
            "SELECT action_name, category FROM conversion_actions WHERE account_id = ? AND status = 'ENABLED'",
            [acct_id],
        )
        conversions = [((r[0] or ""), (r[1] or "")) for r in conv_rows]

        camp_rows = db.fetchall(
            "SELECT DISTINCT campaign_name FROM daily_metrics WHERE account_id = ? AND status = 'ENABLED'",
            [acct_id],
        )
        campaign_names = [(r[0] or "") for r in camp_rows]

        type_rows = db.fetchall(
            "SELECT campaign_type, count(*) FROM daily_metrics WHERE account_id = ? GROUP BY campaign_type",
            [acct_id],
        )
        campaign_types = {(r[0] or "UNKNOWN"): r[1] for r in type_rows}

        result = classify(ClassificationInputs(
            account_id=acct_id,
            account_name=name or "",
            website_url=website or "",
            title_text=title_text,
            description_text=description_text,
            campaign_names=campaign_names,
            campaign_types=campaign_types,
            conversions=conversions,
        ))

        db.execute(
            "UPDATE accounts SET business_type = ?, vertical = ? WHERE account_id = ?",
            [result.business_type.value, result.vertical, acct_id],
        )
        biz_summary[result.business_type.value] = biz_summary.get(result.business_type.value, 0) + 1
        summary[result.vertical or "(none)"] = summary.get(result.vertical or "(none)", 0) + 1
        if result.business_type.value == "unknown":
            unknowns.append((acct_id, name))
        traces.append({
            "account_id": acct_id,
            "account_name": name,
            "business_type": result.business_type.value,
            "vertical": result.vertical,
            "confidence": result.confidence,
            "rule_trace": result.rule_trace,
            "business_type_scores": result.business_type_scores,
            "vertical_scores": result.vertical_scores,
        })

    # Business-type table
    bt_table = Table(title="Business-type distribution", show_header=True, header_style="bold")
    bt_table.add_column("Business type")
    bt_table.add_column("Count", justify="right")
    bt_table.add_column("Share", justify="right")
    for bt, n in sorted(biz_summary.items(), key=lambda x: -x[1]):
        bt_table.add_row(bt, str(n), f"{n/total:.0%}")
    console.print(bt_table)

    # Vertical table
    v_table = Table(title="Vertical distribution", show_header=True, header_style="bold")
    v_table.add_column("Vertical")
    v_table.add_column("Count", justify="right")
    v_table.add_column("Share", justify="right")
    for v, n in sorted(summary.items(), key=lambda x: -x[1]):
        v_table.add_row(v, str(n), f"{n/total:.0%}")
    console.print(v_table)

    console.print(f"\n[bold]Unknown business_type: {len(unknowns)}[/bold] of {total} accounts")
    for aid, n in unknowns[:25]:
        console.print(f"  {aid}  {n}")
    if len(unknowns) > 25:
        console.print(f"  … and {len(unknowns) - 25} more")

    out_path = Path("data/classification_traces.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(traces, indent=2))
    console.print(f"\n[dim]Per-account traces written to {out_path}[/dim]")
    db.close()


if __name__ == "__main__":
    main()
