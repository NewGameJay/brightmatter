"""
CLI for memory ingestion commands.

Usage:
    mh1 memory backfill --client <id> --since <date> [--limit N] [--dry-run] [--yes] [--force]
"""

import argparse
import sys
from pathlib import Path
from typing import List


def main(args: List[str]) -> int:
    """Entry point for `mh1 memory` commands."""
    parser = argparse.ArgumentParser(prog="mh1 memory", description="Memory ingestion commands")
    subparsers = parser.add_subparsers(dest="subcommand")

    # backfill subcommand
    bf = subparsers.add_parser("backfill", help="Backfill memory ingestion for historical runs")
    bf.add_argument("--client", required=True, dest="client_id", help="Client ID to filter runs")
    bf.add_argument("--since", required=True, help="ISO date — only process runs created on/after this date")
    bf.add_argument("--limit", type=int, default=None, help="Max runs to process (default: unlimited)")
    bf.add_argument("--yes", action="store_true", help="Write bundles to disk (default: dry-run)")
    bf.add_argument("--force", action="store_true", help="Re-ingest runs that already have a bundle")

    parsed = parser.parse_args(args)

    if parsed.subcommand is None:
        parser.print_help()
        return 1

    if parsed.subcommand == "backfill":
        return _cmd_backfill(parsed)

    parser.print_help()
    return 1


def _cmd_backfill(args: argparse.Namespace) -> int:
    """Execute the backfill subcommand."""
    from .backfill import backfill_runs

    # Determine project root (walk up from this file)
    project_root = Path(__file__).resolve().parents[3]

    dry_run = not args.yes
    mode_label = "DRY-RUN" if dry_run else "WRITE"

    print(f"\n{'='*60}")
    print(f"Memory Backfill [{mode_label}]")
    print(f"  Client:  {args.client_id}")
    print(f"  Since:   {args.since}")
    print(f"  Limit:   {args.limit or 'unlimited'}")
    print(f"  Force:   {args.force}")
    print(f"{'='*60}\n")

    summary = backfill_runs(
        client_id=args.client_id,
        since=args.since,
        project_root=project_root,
        limit=args.limit,
        dry_run=dry_run,
        force=args.force,
    )

    print(f"\n{'─'*40}")
    print(f"Runs found:           {summary['runs_found']}")
    print(f"Runs processed:       {summary['runs_processed']}")
    print(f"Runs skipped (exist): {summary['runs_skipped_existing']}")
    print(f"Runs skipped (error): {summary['runs_skipped_error']}")
    if summary["errors"]:
        print(f"\nErrors:")
        for err in summary["errors"][:10]:
            print(f"  - {err}")
    print()

    return 0
