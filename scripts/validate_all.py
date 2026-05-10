"""Run every registered disconfirmation harness and produce a single summary.

Output is purely terminal — no DB writes, no external calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from brightmatter.storage.database import Database
from brightmatter.validation import AUDITS

console = Console()


def detector_recommendation(audits: list) -> str:
    """Translate per-signal `overall` distribution into a detector-level call."""
    if not audits:
        return "NO_SIGNALS"
    counts = {"likely_false_positive": 0, "weak_evidence": 0,
              "confirmed_with_caveat": 0, "supported": 0, "well_supported": 0}
    for a in audits:
        counts[a.overall] += 1
    n = len(audits)
    bad = counts["likely_false_positive"] + counts["weak_evidence"]
    good = counts["supported"] + counts["well_supported"]
    if bad > good:
        return "REVISE"
    if counts["likely_false_positive"]:
        return "TIGHTEN"
    if good == n:
        return "KEEP"
    return "MONITOR"


def main():
    db = Database()
    db.initialize()

    summary_rows = []
    for key, fn in AUDITS.items():
        audits = fn(db)
        agg = {"confirm": 0, "disconfirm": 0, "inconclusive": 0}
        per_signal_overall = {"likely_false_positive": 0, "weak_evidence": 0,
                              "confirmed_with_caveat": 0, "supported": 0, "well_supported": 0}
        for a in audits:
            for r in a.test_results:
                agg[r.verdict] += 1
            per_signal_overall[a.overall] += 1
        rec = detector_recommendation(audits)
        summary_rows.append({
            "key": key,
            "n_signals": len(audits),
            "confirm": agg["confirm"],
            "disconfirm": agg["disconfirm"],
            "inconclusive": agg["inconclusive"],
            "well_supported": per_signal_overall["well_supported"],
            "supported": per_signal_overall["supported"],
            "with_caveat": per_signal_overall["confirmed_with_caveat"],
            "weak_evidence": per_signal_overall["weak_evidence"],
            "false_positive": per_signal_overall["likely_false_positive"],
            "recommendation": rec,
        })

    # Render
    rec_style = {
        "KEEP": "green bold",
        "MONITOR": "yellow",
        "TIGHTEN": "yellow bold",
        "REVISE": "red bold",
        "NO_SIGNALS": "dim",
    }
    table = Table(title=f"Cross-detector validation summary ({len(summary_rows)} detectors)",
                  show_header=True, header_style="bold")
    table.add_column("Detector", style="cyan")
    table.add_column("Signals", justify="right")
    table.add_column("Confirm", justify="right", style="green")
    table.add_column("Disconfirm", justify="right", style="red")
    table.add_column("Inconc", justify="right", style="yellow")
    table.add_column("Well", justify="right")
    table.add_column("Sup", justify="right")
    table.add_column("Caveat", justify="right")
    table.add_column("Weak", justify="right")
    table.add_column("FalsePos", justify="right", style="red")
    table.add_column("Verdict")
    for r in summary_rows:
        table.add_row(
            r["key"], str(r["n_signals"]),
            str(r["confirm"]), str(r["disconfirm"]), str(r["inconclusive"]),
            str(r["well_supported"]), str(r["supported"]),
            str(r["with_caveat"]), str(r["weak_evidence"]), str(r["false_positive"]),
            f"[{rec_style.get(r['recommendation'], '')}]{r['recommendation']}[/]",
        )
    console.print(table)

    # Top-line verdicts
    keep = [r["key"] for r in summary_rows if r["recommendation"] == "KEEP"]
    monitor = [r["key"] for r in summary_rows if r["recommendation"] == "MONITOR"]
    tighten = [r["key"] for r in summary_rows if r["recommendation"] == "TIGHTEN"]
    revise = [r["key"] for r in summary_rows if r["recommendation"] == "REVISE"]
    no_sig = [r["key"] for r in summary_rows if r["recommendation"] == "NO_SIGNALS"]

    panel = (
        f"[green]KEEP ({len(keep)}):[/] {', '.join(keep) or '—'}\n"
        f"[yellow]MONITOR ({len(monitor)}):[/] {', '.join(monitor) or '—'}\n"
        f"[yellow bold]TIGHTEN ({len(tighten)}):[/] {', '.join(tighten) or '—'}\n"
        f"[red bold]REVISE ({len(revise)}):[/] {', '.join(revise) or '—'}\n"
        f"[dim]NO_SIGNALS ({len(no_sig)}):[/] {', '.join(no_sig) or '—'}"
    )
    console.print(Panel(panel, title="Detector verdicts"))
    db.close()


if __name__ == "__main__":
    main()
