"""BrightMatter CLI — the primary interface for running ingestion, analysis, and exploration.

Usage:
    python -m brightmatter discover       # Find accounts from MCC (or generate demo)
    python -m brightmatter ingest         # Pull daily metrics for all accounts
    python -m brightmatter ingest --days 90  # Pull 90 days of history
    python -m brightmatter analyze        # Run detectors + agents
    python -m brightmatter analyze --detectors-only  # Layer 1 only (no LLM)
    python -m brightmatter accounts       # List all accounts
    python -m brightmatter signals        # View detected signals
    python -m brightmatter patterns       # View recorded patterns
    python -m brightmatter episodes       # View change→outcome episodes
    python -m brightmatter audit <id>     # Deep audit of one account (LLM)
    python -m brightmatter validate <detector>  # Disconfirmation harness
    python -m brightmatter status         # Overall system status
"""

from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from brightmatter.analysis.engine import AnalysisEngine
from brightmatter.ingestion.pipeline import IngestionPipeline
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

console = Console()


def _setup(verbose: bool = False) -> tuple[Database, Repository]:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(name)s | %(message)s")
    db = Database()
    db.initialize()
    return db, Repository(db)


# ── Commands ──

def cmd_discover(args):
    db, repo = _setup(args.verbose)
    pipeline = IngestionPipeline(repo)

    mode = "live" if pipeline.is_live else "demo"
    console.print(f"\n[bold]Discovering accounts[/bold] (mode: {mode})\n")

    accounts = pipeline.discover_accounts()
    table = Table(title=f"Discovered {len(accounts)} Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Vertical")
    table.add_column("Spend Tier")

    for a in accounts:
        table.add_row(a.account_id, a.account_name, a.business_type.value,
                       a.vertical, a.spend_tier.value)
    console.print(table)
    db.close()


def cmd_ingest(args):
    db, repo = _setup(args.verbose)
    pipeline = IngestionPipeline(repo)

    console.print(f"\n[bold]Ingesting data[/bold] ({args.days} days, {'live' if pipeline.is_live else 'demo'} mode)\n")

    with console.status("Pulling daily metrics..."):
        daily = pipeline.ingest_daily(days=args.days)
    console.print(f"  Daily metrics: {sum(daily.values())} rows across {len(daily)} accounts")

    if args.keywords:
        with console.status("Pulling keyword data..."):
            kw = pipeline.ingest_keywords(days=min(args.days, 7))
        console.print(f"  Keyword metrics: {sum(kw.values())} rows")

    if args.changes:
        with console.status("Pulling change history..."):
            ch = pipeline.ingest_changes(days=min(args.days, 90))
        console.print(f"  Change events: {sum(ch.values())} events")

    if args.search_terms:
        with console.status("Pulling search terms..."):
            st = pipeline.ingest_search_terms(days=min(args.days, 30))
        console.print(f"  Search-term rows: {sum(st.values())} terms")

    console.print("\n[green]Ingestion complete.[/green]")
    db.close()


def cmd_analyze(args):
    db, repo = _setup(args.verbose)
    engine = AnalysisEngine(db, repo)

    console.print("\n[bold]Running analysis...[/bold]\n")

    if args.detectors_only:
        signals = engine.run_detectors_only()
        _print_signals(signals)
    else:
        results = engine.run_full_analysis(use_agents=not args.no_agents)
        console.print(Panel(
            f"Signals: {results.get('signals', 0)}\n"
            f"Patterns: {results.get('patterns', 0)}\n"
            f"Episodes: {results.get('episodes', 0)}",
            title="Analysis Results",
        ))
        if results.get("agent_analysis"):
            console.print(f"\nAgent diagnoses: {results['agent_analysis'].get('diagnoses', 0)}")
    db.close()


def cmd_accounts(args):
    db, repo = _setup(args.verbose)
    accounts = repo.list_accounts()
    if not accounts:
        console.print("[yellow]No accounts found. Run 'discover' first.[/yellow]")
        db.close()
        return

    table = Table(title=f"{len(accounts)} Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Vertical")
    table.add_column("Spend Tier")
    table.add_column("Last Updated")

    for a in accounts:
        table.add_row(a.account_id, a.account_name, a.business_type.value,
                       a.vertical, a.spend_tier.value,
                       str(a.last_updated)[:10] if a.last_updated else "—")
    console.print(table)
    db.close()


def cmd_signals(args):
    db, repo = _setup(args.verbose)
    data = repo.get_signals(account_id=args.account, domain=args.domain)

    if not data or not data.get("signal_id"):
        console.print("[yellow]No signals found. Run 'analyze' first.[/yellow]")
        db.close()
        return

    table = Table(title="Detected Signals")
    table.add_column("Severity", style="bold")
    table.add_column("Account")
    table.add_column("Domain")
    table.add_column("Type")
    table.add_column("Message")

    sev_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}
    for i in range(min(len(data["signal_id"]), args.limit)):
        sev = data["severity"][i]
        table.add_row(
            f"[{sev_style.get(sev, '')}]{sev}[/]",
            data["account_id"][i],
            data["domain"][i],
            data["signal_type"][i],
            data["message"][i][:100] if data["message"][i] else "",
        )
    console.print(table)
    db.close()


def cmd_patterns(args):
    db, repo = _setup(args.verbose)
    data = repo.get_patterns(domain=args.domain, min_confidence=args.min_confidence)

    if not data or not data.get("pattern_id"):
        console.print("[yellow]No patterns found. Run 'analyze' first.[/yellow]")
        db.close()
        return

    table = Table(title="Recorded Patterns")
    table.add_column("Severity")
    table.add_column("Domain")
    table.add_column("Type")
    table.add_column("Confidence")
    table.add_column("Summary")

    sev_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}
    for i in range(min(len(data["pattern_id"]), args.limit)):
        sev = data["severity"][i]
        table.add_row(
            f"[{sev_style.get(sev, '')}]{sev}[/]",
            data["domain"][i],
            data["pattern_type"][i],
            f"{data['confidence'][i]:.0%}",
            data["summary"][i][:120] if data["summary"][i] else "",
        )
    console.print(table)
    db.close()


def cmd_episodes(args):
    db, repo = _setup(args.verbose)
    data = repo.get_episodes(account_id=args.account, outcome=args.outcome)

    if not data or not data.get("episode_id"):
        console.print("[yellow]No episodes found. Run 'analyze' after ingesting changes.[/yellow]")
        db.close()
        return

    from rich.markup import escape

    table = Table(title="Episodes (Change → Outcome)")
    table.add_column("Account")
    table.add_column("Change")
    table.add_column("Outcome", style="bold")
    table.add_column("Conf?")
    table.add_column("Magnitude")
    table.add_column("Detail")

    outcome_style = {"improved": "green", "degraded": "red", "neutral": "dim",
                     "confounded": "magenta", "pending": "yellow"}
    n = len(data["episode_id"])
    has = lambda k: k in data  # noqa: E731 — new columns may be absent on old DBs
    for i in range(min(n, args.limit)):
        out = data["outcome"][i] or ""
        style = outcome_style.get(out, "white")
        confounded = bool(data["confounded"][i]) if has("confounded") else False
        table.add_row(
            escape(data["account_id"][i] or ""),
            escape((data["change_description"][i] or "")[:48]),
            f"[{style}]{escape(out)}[/{style}]",
            "[magenta]✓[/magenta]" if confounded else "",
            f"{data['outcome_magnitude'][i]:.0%}" if data["outcome_magnitude"][i] else "—",
            escape((data["outcome_detail"][i] or "")[:60]),
        )
    console.print(table)
    db.close()


def cmd_bundles(args):
    from brightmatter.patterns.bundle_cards import analyze_bundles

    db, repo = _setup(args.verbose)
    cards = analyze_bundles(db, min_episodes=args.min)
    if not cards:
        console.print("[yellow]No bundle cards. Run 'analyze' (episodes) first.[/yellow]")
        db.close()
        return

    conf_style = {"RELIABLE": "green", "DIRECTIONAL": "yellow", "LOW": "dim"}
    console.print("\n[bold]Bundle → Performance cards[/bold] "
                  "[dim](clean/attributable episodes only · PRELIMINARY — no trend adjustment, Phase 2)[/dim]\n")
    for c in cards:
        n = c["n"]
        imp, deg, neu = c["improved"], c["degraded"], c["neutral"]
        head = f"{c['category']}  [dim]({c['actor']})[/dim]"
        console.print(f"[bold cyan]{head}[/bold cyan]  "
                      f"[{conf_style.get(c['confidence'],'')}]{c['confidence']}[/]  "
                      f"n={n}, {c['accounts']} accounts")
        console.print(f"  improved {imp} ({imp/n:.0%}, avg {c['avg_improve_mag']:.0%}) · "
                      f"degraded {deg} ({deg/n:.0%}, avg {c['avg_degrade_mag']:.0%}) · "
                      f"neutral {neu} ({neu/n:.0%})")
        if c["by_vertical"]:
            vs = ", ".join(f"{k} {v['improved_pct']:.0%}↑ (n={v['n']})"
                           for k, v in list(c["by_vertical"].items())[:4])
            console.print(f"  [dim]vertical:[/dim] {vs}")
        if c["by_tier"]:
            ts = ", ".join(f"{k} {v['improved_pct']:.0%}↑ (n={v['n']})"
                           for k, v in list(c["by_tier"].items())[:4])
            console.print(f"  [dim]spend tier:[/dim] {ts}")
        console.print()
    console.print("[dim]Confidence: RELIABLE n≥30/8+ accts · DIRECTIONAL n≥10/4+ · LOW otherwise. "
                  "Outcomes are pre-trend-adjustment; pre-existing trajectory not yet isolated.[/dim]")
    db.close()


def cmd_trends(args):
    from brightmatter.analysis.trends import profile_volatility, run_trends

    db, repo = _setup(args.verbose)
    if not args.no_recompute:
        with console.status("Computing rolling trends (OLS, 7/14/30d)…"):
            n = run_trends(db)
            profile_volatility(db)
        console.print(f"  Computed {n} trend rows (+ volatility profiles).\n")
    table = Table(title="Trend classifications (14-day window)")
    table.add_column("Metric")
    for c in ("improving", "declining", "rising", "falling", "stable", "volatile"):
        table.add_column(c, justify="right")
    rows = db.fetchdf("""
        SELECT metric, classification, count(*) n FROM campaign_trends
        WHERE window_days = 14 GROUP BY 1, 2
    """)
    grid: dict[str, dict[str, int]] = {}
    for i in range(len(rows.get("metric", []))):
        grid.setdefault(rows["metric"][i], {})[rows["classification"][i]] = rows["n"][i]
    for metric in ("cpa", "cvr", "ctr", "roas", "impression_share", "cost"):
        g = grid.get(metric, {})
        table.add_row(metric, *[str(g.get(c, 0)) for c in
                                ("improving", "declining", "rising", "falling", "stable", "volatile")])
    console.print(table)
    db.close()


def cmd_audit(args):
    db, repo = _setup(args.verbose)
    engine = AnalysisEngine(db, repo)

    console.print(f"\n[bold]Auditing account {args.account_id}...[/bold]\n")
    result = engine.audit_account(args.account_id)

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        db.close()
        return

    console.print(Panel(
        f"Health Score: {result.get('health_score', 0)}/100\n\n"
        f"{result.get('summary', '')}\n\n"
        f"Top Opportunity: {result.get('top_opportunity', '—')}\n"
        f"Biggest Risk: {result.get('biggest_risk', '—')}",
        title=f"Account Audit: {args.account_id}",
    ))

    if result.get("findings"):
        table = Table(title="Findings")
        table.add_column("Severity")
        table.add_column("Domain")
        table.add_column("Finding")
        table.add_column("Recommendation")
        for f in result["findings"]:
            table.add_row(f["severity"], f["domain"], f["finding"], f["recommendation"])
        console.print(table)
    db.close()


def cmd_validate(args):
    from brightmatter.validation import AUDITS

    db, _repo = _setup(args.verbose)
    audit_fn = AUDITS.get(args.detector)
    if audit_fn is None:
        console.print(
            f"[red]Unknown detector '{args.detector}'.[/red] "
            f"Supported: {', '.join(sorted(AUDITS.keys()))}"
        )
        db.close()
        return

    console.print(f"\n[bold]Disconfirmation harness — {args.detector}[/bold]\n")
    audits = audit_fn(db)

    if not audits:
        console.print("[yellow]No roas_contamination signals to audit. Run 'analyze' first.[/yellow]")
        db.close()
        return

    verdict_style = {
        "confirm": "green", "disconfirm": "red bold", "inconclusive": "yellow",
    }
    overall_style = {
        "well_supported": "green bold", "supported": "green",
        "confirmed_with_caveat": "yellow", "weak_evidence": "yellow",
        "likely_false_positive": "red bold",
    }
    aggregate: dict[str, dict[str, int]] = {}

    for a in audits:
        c = a.verdict_counts
        biz = getattr(a, "business_type", None)
        camp = getattr(a, "campaign_id", None)
        tokens = getattr(a, "brand_tokens_used", None)
        meta_lines = []
        if biz:
            meta_lines.append(f"biz_type=[dim]{biz}[/]")
        if camp:
            meta_lines.append(f"campaign=[dim]{camp}[/]")
        if tokens is not None:
            meta_lines.append(f"brand_tokens={tokens or '[]'}")
        meta = "  ".join(meta_lines)
        header = (
            f"[cyan]{a.account_id}[/] [bold]{a.account_name or '(unnamed)'}[/]"
            + (f"  {meta}" if meta else "")
            + f"\n[dim]{a.detector_message}[/]\n"
            + f"verdicts: confirm={c['confirm']} disconfirm={c['disconfirm']} inconclusive={c['inconclusive']}  →  "
            + f"[{overall_style.get(a.overall, '')}]{a.overall}[/]"
        )
        console.print(Panel(header, title=f"Signal {a.signal_id}"))

        t = Table(show_header=True, header_style="bold")
        t.add_column("Test", style="cyan")
        t.add_column("Verdict")
        t.add_column("Summary")
        for r in a.test_results:
            t.add_row(
                f"{r.test_id} {r.test_name}",
                f"[{verdict_style.get(r.verdict, '')}]{r.verdict}[/]",
                r.summary,
            )
            agg = aggregate.setdefault(r.test_id, {"confirm": 0, "disconfirm": 0, "inconclusive": 0, "name": r.test_name})
            agg[r.verdict] += 1
        console.print(t)

        if args.show_evidence:
            for r in a.test_results:
                if not r.evidence:
                    continue
                console.print(f"\n  [dim]{r.test_id} evidence:[/]")
                for row in r.evidence[:5]:
                    console.print(f"    {row}")

    # Cross-signal aggregate
    n = len(audits)
    agg_table = Table(title=f"Aggregate across {n} signal(s)", show_header=True, header_style="bold")
    agg_table.add_column("Test", style="cyan")
    agg_table.add_column("Confirm", justify="right")
    agg_table.add_column("Disconfirm", justify="right", style="red")
    agg_table.add_column("Inconclusive", justify="right", style="yellow")
    agg_table.add_column("Recommendation")
    for tid in sorted(aggregate.keys()):
        a = aggregate[tid]
        rec = _recommendation(a, n)
        agg_table.add_row(
            f"{tid} {a['name']}",
            str(a["confirm"]), str(a["disconfirm"]), str(a["inconclusive"]),
            rec,
        )
    console.print()
    console.print(agg_table)

    # Detector-level recommendation
    overall_counts = {"likely_false_positive": 0, "weak_evidence": 0,
                      "confirmed_with_caveat": 0, "supported": 0, "well_supported": 0}
    for a in audits:
        overall_counts[a.overall] += 1
    bad = overall_counts["likely_false_positive"] + overall_counts["weak_evidence"]
    good = overall_counts["supported"] + overall_counts["well_supported"]
    if bad > good:
        verdict = "[red bold]REVISE[/]: more signals lacked support than had it"
    elif overall_counts["likely_false_positive"]:
        verdict = "[yellow]TIGHTEN[/]: some signals look like false positives — add disconfirming guards"
    elif good == n:
        verdict = "[green]KEEP[/]: every audited signal is supported by adjacent data"
    else:
        verdict = "[yellow]MONITOR[/]: mixed evidence — re-run with more signals"
    console.print(Panel(verdict, title="Detector recommendation"))

    db.close()


def _recommendation(agg: dict, n: int) -> str:
    if agg["disconfirm"] > agg["confirm"]:
        return "Test fails more than it passes — heuristic is unreliable"
    if agg["disconfirm"] >= 1 and agg["confirm"] >= 1:
        return "Mixed — investigate disconfirming cases"
    if agg["confirm"] == n:
        return "Holds across all signals"
    if agg["inconclusive"] == n:
        return "Need more data to evaluate"
    return "Partial signal — keep observing"


def cmd_status(args):
    db, repo = _setup(args.verbose)
    accounts = repo.list_accounts()

    row = db.fetchone("SELECT count(*), min(date), max(date) FROM daily_metrics")
    metrics_count, min_date, max_date = row if row else (0, None, None)

    sig_row = db.fetchone("SELECT count(*) FROM signals")
    pat_row = db.fetchone("SELECT count(*) FROM patterns")
    ep_row = db.fetchone("SELECT count(*) FROM episodes")
    ch_row = db.fetchone("SELECT count(*) FROM change_events")

    console.print(Panel(
        f"Accounts:       {len(accounts)}\n"
        f"Daily metrics:  {metrics_count} rows ({min_date} to {max_date})\n"
        f"Change events:  {ch_row[0] if ch_row else 0}\n"
        f"Signals:        {sig_row[0] if sig_row else 0}\n"
        f"Patterns:       {pat_row[0] if pat_row else 0}\n"
        f"Episodes:       {ep_row[0] if ep_row else 0}\n"
        f"\nMode: {'live' if IngestionPipeline(repo).is_live else 'demo'}\n"
        f"LLM agents: {'available' if AnalysisEngine(db, repo).agent_runner.is_available else 'unavailable (set ANTHROPIC_API_KEY)'}",
        title="BrightMatter Status",
    ))
    db.close()


def _print_signals(signals):
    if not signals:
        console.print("[green]No signals detected — all clear.[/green]")
        return

    table = Table(title=f"{len(signals)} Signals Detected")
    table.add_column("Severity", style="bold")
    table.add_column("Account")
    table.add_column("Domain")
    table.add_column("Message")

    sev_style = {"critical": "red bold", "warning": "yellow", "info": "dim"}
    for s in signals:
        table.add_row(
            f"[{sev_style.get(s.severity.value, '')}]{s.severity.value}[/]",
            s.account_id, s.domain.value, s.message[:100],
        )
    console.print(table)


# ── Main ──

def main():
    parser = argparse.ArgumentParser(prog="brightmatter", description="BrightMatter — Google Ads pattern recognition")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("discover", help="Discover accounts from MCC")

    p_ingest = sub.add_parser("ingest", help="Ingest data from accounts")
    p_ingest.add_argument("--days", type=int, default=30)
    p_ingest.add_argument("--keywords", action="store_true", help="Also pull keyword QS data")
    p_ingest.add_argument("--changes", action="store_true", help="Also pull change history")
    p_ingest.add_argument("--search-terms", action="store_true", help="Also pull search-term performance")

    p_analyze = sub.add_parser("analyze", help="Run analysis pipeline")
    p_analyze.add_argument("--detectors-only", action="store_true")
    p_analyze.add_argument("--no-agents", action="store_true")

    sub.add_parser("accounts", help="List all accounts")

    p_signals = sub.add_parser("signals", help="View detected signals")
    p_signals.add_argument("--account", default=None)
    p_signals.add_argument("--domain", default=None)
    p_signals.add_argument("--limit", type=int, default=50)

    p_patterns = sub.add_parser("patterns", help="View recorded patterns")
    p_patterns.add_argument("--domain", default=None)
    p_patterns.add_argument("--min-confidence", type=float, default=0.0)
    p_patterns.add_argument("--limit", type=int, default=50)

    p_episodes = sub.add_parser("episodes", help="View episodes")
    p_episodes.add_argument("--account", default=None)
    p_episodes.add_argument("--outcome", default=None)
    p_episodes.add_argument("--limit", type=int, default=50)

    p_bundles = sub.add_parser("bundles", help="Bundle → performance cards (Phase 1.75)")
    p_bundles.add_argument("--min", type=int, default=10, help="Min clean episodes per card")

    p_trends = sub.add_parser("trends", help="Compute/view rolling trends (Phase 2.1)")
    p_trends.add_argument("--no-recompute", action="store_true", help="View existing, don't recompute")

    p_audit = sub.add_parser("audit", help="Deep audit of one account (LLM)")
    p_audit.add_argument("account_id")

    p_validate = sub.add_parser("validate", help="Run disconfirmation harness against a detector")
    p_validate.add_argument("detector", help="Detector key (e.g., brand_nonbrand)")
    p_validate.add_argument("--show-evidence", action="store_true", help="Print per-test evidence rows")

    sub.add_parser("status", help="System status")

    args = parser.parse_args()

    cmd_map = {
        "discover": cmd_discover,
        "ingest": cmd_ingest,
        "analyze": cmd_analyze,
        "accounts": cmd_accounts,
        "signals": cmd_signals,
        "patterns": cmd_patterns,
        "episodes": cmd_episodes,
        "bundles": cmd_bundles,
        "trends": cmd_trends,
        "audit": cmd_audit,
        "validate": cmd_validate,
        "status": cmd_status,
    }

    try:
        cmd_map[args.command](args)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        if args.verbose:
            console.print_exception()
        sys.exit(1)
