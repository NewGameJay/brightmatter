"""
Fireflies ingestion — CLI entry point

Commands:
    mh1 fireflies sync              Sync all new meetings since last sync
    mh1 fireflies sync --backfill   Re-process meetings from the past 90 days
    mh1 fireflies sync --days 30    Re-process meetings from the past N days
    mh1 fireflies ingest <id>       Process a specific meeting by Fireflies ID
    mh1 fireflies status            Show sync status and recent ingestions
    mh1 fireflies search <query>    Search ingested meetings by concept/keyword
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import List


def main(args: List[str]) -> int:
    """CLI entry point for Fireflies ingestion commands."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args:
        _print_help()
        return 0

    subcmd = args[0]

    if subcmd == "sync":
        return _cmd_sync(args[1:])
    elif subcmd == "ingest":
        return _cmd_ingest(args[1:])
    elif subcmd == "status":
        return _cmd_status(args[1:])
    elif subcmd == "search":
        return _cmd_search(args[1:])
    elif subcmd in ("--help", "-h", "help"):
        _print_help()
        return 0
    else:
        print(f"Unknown subcommand: {subcmd}")
        _print_help()
        return 1


def _cmd_sync(args: List[str]) -> int:
    """Sync new meetings or backfill historical ones."""
    from lib.fireflies.config import FirefliesConfig

    config = FirefliesConfig.from_env()
    err = config.validate()
    if err:
        print(f"Error: {err}")
        print("Set FIREFLIES_API_KEY in your .env file")
        return 1

    backfill = "--backfill" in args
    force = "--force" in args

    days = 90
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])

    if backfill:
        from lib.fireflies.ingest import backfill as do_backfill
        print(f"Backfilling meetings from the past {days} days...")
        result = do_backfill(since_days=days, config=config, force=force)
    else:
        from lib.fireflies.ingest import sync_new
        print("Syncing new meetings...")
        result = sync_new(config=config)

    print(f"\nResults:")
    print(f"  Found:    {result.meetings_found}")
    print(f"  Ingested: {result.meetings_ingested}")
    print(f"  Filtered: {result.meetings_filtered}")
    print(f"  Skipped:  {result.meetings_skipped}")
    print(f"  Errors:   {result.meetings_errored}")
    print(f"  Insights: {result.total_insights}")
    print(f"  Connections: {result.total_connections}")
    print(f"  Knowledge cards: {result.total_knowledge_cards}")
    print(f"  Duration: {result.duration_ms}ms")

    if result.meetings_errored > 0:
        print("\nErrors:")
        for r in result.results:
            if r.status == "error":
                print(f"  {r.meeting_id}: {r.error}")

    return 0


def _cmd_ingest(args: List[str]) -> int:
    """Process a specific meeting by Fireflies ID."""
    if not args:
        print("Usage: mh1 fireflies ingest <meeting_id> [--force]")
        return 1

    meeting_id = args[0]
    force = "--force" in args

    from lib.fireflies.ingest import ingest_meeting
    print(f"Ingesting meeting {meeting_id}...")
    result = ingest_meeting(meeting_id, force=force)

    print(f"\nResult: {result.status}")
    if result.title:
        print(f"  Title: {result.title}")
    if result.classification:
        print(f"  Type: {result.classification.meeting_type}")
        if result.classification.client_id:
            print(f"  Client: {result.classification.client_name} ({result.classification.client_id})")
    print(f"  Insights: {result.insights_count}")
    print(f"  Connections: {result.connections_count}")
    print(f"  Knowledge cards: {result.knowledge_cards_count}")
    if result.error:
        print(f"  Error: {result.error}")

    return 0 if result.status != "error" else 1


def _cmd_status(args: List[str]) -> int:
    """Show sync status and recent ingestions."""
    from lib.fireflies.store import get_last_sync_timestamp, list_transcripts

    last_sync = get_last_sync_timestamp()
    if last_sync:
        sync_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(last_sync))
        print(f"Last sync: {sync_time}")
    else:
        print("Last sync: never")

    print("\nRecent ingestions:")
    transcripts = list_transcripts(limit=10)
    if not transcripts:
        print("  (none)")
    else:
        for t in transcripts:
            cls = t.get("classification", {})
            meeting_type = cls.get("meeting_type", "?")
            client = cls.get("client_name", "")
            date_iso = t.get("date_iso", "")
            title = t.get("title", "untitled")
            insights = len(t.get("insight_ids", []))
            connections = len(t.get("connection_ids", []))

            label = f"[{meeting_type}]"
            if client:
                label += f" {client}"

            print(f"  {date_iso[:10]}  {label:30s}  {title[:50]:50s}  {insights}i {connections}c")

    return 0


def _cmd_search(args: List[str]) -> int:
    """Search ingested meetings by concept or keyword."""
    if not args:
        print("Usage: mh1 fireflies search <concept_or_keyword>")
        return 1

    query = args[0].lower().replace(" ", "_")

    from lib.fireflies.store import get_connections_by_concept, get_existing_insights

    print(f"Searching for concept: {query}\n")

    # Search insights
    all_insights = get_existing_insights(domains=None, limit=500)
    matching = [
        i for i in all_insights
        if query in " ".join(i.get("concepts", [])).lower()
        or query.replace("_", " ") in i.get("content", "").lower()
        or query.replace("_", " ") in i.get("title", "").lower()
    ]

    if matching:
        print(f"Found {len(matching)} matching insights:")
        for i in matching[:20]:
            print(f"  [{i.get('insight_type', '?')}] {i.get('title', '')}")
            print(f"    Speaker: {i.get('speaker', '?')} | Meeting: {i.get('meeting_id', '?')}")
            print(f"    Concepts: {', '.join(i.get('concepts', []))}")
            print()
    else:
        print("No matching insights found.")

    # Search connections
    connections = get_connections_by_concept(query)
    if connections:
        print(f"\nFound {len(connections)} cross-call connections:")
        for c in connections:
            print(f"  [{c.get('pattern_type', '?')}] {c.get('title', '')}")
            print(f"    Strength: {c.get('strength', 0):.2f}")
            print(f"    Meetings: {', '.join(c.get('meeting_ids', []))}")
            print(f"    {c.get('description', '')[:120]}")
            print()

    return 0


def _print_help() -> None:
    print("""
Fireflies.ai Meeting Intelligence

Commands:
  sync                 Sync all new meetings since last sync
  sync --backfill      Re-process meetings from the past 90 days
  sync --days N        Re-process meetings from the past N days
  sync --force         Re-process even if already ingested
  ingest <id>          Process a specific meeting by Fireflies ID
  ingest <id> --force  Re-process a specific meeting
  status               Show sync status and recent ingestions
  search <concept>     Search ingested meetings by concept/keyword

Environment:
  FIREFLIES_API_KEY           Required. Your Fireflies.ai API key.
  FIREFLIES_WEBHOOK_SECRET    Optional. HMAC secret for webhook verification.
  ANTHROPIC_API_KEY           Required for insight extraction (uses Haiku).
""".strip())
