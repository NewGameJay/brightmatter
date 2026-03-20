"""
Expert Knowledge CLI (Package I3)

Commands:
- add-source: Register a knowledge source file
- ingest: Parse sources into knowledge cards
- list-cards: Show card index
- list-sources: Show registered sources
- inspect-binding: Preview binding for a plan/node
"""

import argparse
import json
import sys
from pathlib import Path


def _get_project_root() -> Path:
    """Get project root from env or cwd."""
    import os
    return Path(os.environ.get("MH1_PROJECT_ROOT", ".")).resolve()


def cmd_add_source(args) -> int:
    """Register a knowledge source file."""
    from lib.execution.knowledge.store import KnowledgeStore

    project_root = _get_project_root()
    store = KnowledgeStore(str(project_root / "knowledge_store"))

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    if not domains:
        print("Error: At least one domain is required", file=sys.stderr)
        return 1

    try:
        source_id = store.add_source(
            file_path=str(file_path),
            title=args.title,
            domains=domains,
            format=args.format,
            author=args.author or "unknown",
            trust_level=args.trust_level or "unreviewed",
            reviewed_by=args.reviewed_by,
            valid_until=args.valid_until,
            allowed_clients=[c.strip() for c in args.allowed_clients.split(",")] if args.allowed_clients else None,
        )
        print(f"Source registered: {source_id}")
        print(f"  Title: {args.title}")
        print(f"  Domains: {domains}")
        print(f"  Trust: {args.trust_level or 'unreviewed'}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error registering source: {e}", file=sys.stderr)
        return 1


def cmd_ingest(args) -> int:
    """Parse sources into knowledge cards."""
    from lib.execution.knowledge.store import KnowledgeStore
    from lib.execution.knowledge.ingest import ingest_source_to_cards, reingest_source

    project_root = _get_project_root()
    store = KnowledgeStore(str(project_root / "knowledge_store"))

    if args.source:
        # Ingest a specific source
        if args.force:
            result = reingest_source(args.source, store, force=True, dry_run=args.dry_run)
        else:
            source = store.get_source(args.source)
            if not source:
                print(f"Error: Source not found: {args.source}", file=sys.stderr)
                return 1
            raw_path = store.get_raw_path(args.source)
            if not raw_path:
                print(f"Error: Raw file not found for: {args.source}", file=sys.stderr)
                return 1
            result = ingest_source_to_cards(raw_path, source, store, dry_run=args.dry_run)

        prefix = "[DRY RUN] " if args.dry_run else ""
        print(f"{prefix}Ingest result for {args.source}:")
        print(f"  Cards created: {result.cards_created}")
        print(f"  Cards skipped: {result.cards_skipped}")
        if result.errors:
            for err in result.errors:
                print(f"  ERROR: {err}", file=sys.stderr)
        if result.warnings:
            for warn in result.warnings:
                print(f"  WARNING: {warn}")
        if result.card_ids:
            print(f"  Card IDs: {result.card_ids}")
        return 1 if result.errors else 0

    elif args.all:
        # Ingest all active sources
        sources = store.list_sources(status="active")
        if not sources:
            print("No active sources found.")
            return 0

        total_created = 0
        total_errors = 0
        for source in sources:
            source_id = source["source_id"]
            raw_path = store.get_raw_path(source_id)
            if not raw_path:
                print(f"  Skipping {source_id}: raw file not found")
                continue

            if args.force:
                result = reingest_source(source_id, store, force=True, dry_run=args.dry_run)
            else:
                result = ingest_source_to_cards(raw_path, source, store, dry_run=args.dry_run)

            prefix = "[DRY RUN] " if args.dry_run else ""
            print(f"{prefix}{source_id}: {result.cards_created} cards created")
            total_created += result.cards_created
            if result.errors:
                total_errors += len(result.errors)
                for err in result.errors:
                    print(f"  ERROR: {err}", file=sys.stderr)

        print(f"\nTotal: {total_created} cards created, {total_errors} errors")
        return 1 if total_errors > 0 else 0

    else:
        print("Error: Specify --source <source_id> or --all", file=sys.stderr)
        return 1


def cmd_list_cards(args) -> int:
    """Show card index."""
    from lib.execution.knowledge.store import KnowledgeStore

    project_root = _get_project_root()
    store = KnowledgeStore(str(project_root / "knowledge_store"))

    cards = store.list_cards(domain=args.domain, card_type=args.type)

    if args.json:
        print(json.dumps(cards, indent=2))
    else:
        if not cards:
            print("No cards found.")
            return 0

        print(f"Knowledge Cards ({len(cards)} total):")
        print("-" * 60)
        for card in cards:
            trust = card.get("trust_level", "unreviewed")
            domains = ", ".join(card.get("domains", []))
            print(f"  [{card.get('card_type', 'definition')}] {card.get('title', 'Untitled')}")
            print(f"    ID: {card.get('card_id')}  Trust: {trust}")
            print(f"    Domains: {domains}")
            print(f"    Source: {card.get('source_id')}")
            print()

    return 0


def cmd_list_sources(args) -> int:
    """Show registered sources."""
    from lib.execution.knowledge.store import KnowledgeStore

    project_root = _get_project_root()
    store = KnowledgeStore(str(project_root / "knowledge_store"))

    sources = store.list_sources(status="active")

    if args.json:
        print(json.dumps(sources, indent=2))
    else:
        if not sources:
            print("No active sources found.")
            return 0

        print(f"Knowledge Sources ({len(sources)} active):")
        print("-" * 60)
        for s in sources:
            domains = ", ".join(s.get("domains", []))
            print(f"  {s.get('source_id')}: {s.get('title')}")
            print(f"    Format: {s.get('format')}  Trust: {s.get('trust_level', 'unreviewed')}")
            print(f"    Domains: {domains}")
            print(f"    Author: {s.get('author', 'unknown')}")
            print()

    return 0


def cmd_inspect_binding(args) -> int:
    """Preview binding for a plan/node."""
    from lib.execution.knowledge import KnowledgeConfig
    from lib.execution.knowledge.bind import resolve_cards_for_node

    project_root = _get_project_root()
    plan_path = Path(args.plan).resolve()

    if not plan_path.exists():
        print(f"Error: Plan not found: {args.plan}", file=sys.stderr)
        return 1

    try:
        plan = json.loads(plan_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in plan: {e}", file=sys.stderr)
        return 1

    nodes = plan.get("nodes", {})
    config = KnowledgeConfig.from_features(plan.get("features"))
    # Enable for inspection even if plan doesn't have it enabled
    config.enabled = True

    store_dir = project_root / "knowledge_store"
    cards_index_path = str(store_dir / "cards_index.json")
    cards_dir = str(store_dir / "cards")

    node_ids = [args.node] if args.node else list(nodes.keys())

    for node_id in node_ids:
        node_config = nodes.get(node_id, {})
        if not node_config:
            print(f"  Node {node_id}: not found in plan")
            continue

        binding = resolve_cards_for_node(
            node_config=node_config,
            cards_index_path=cards_index_path,
            cards_dir=cards_dir,
            config=config,
        )

        if args.json:
            print(json.dumps({
                "node_id": node_id,
                "cards_matched": len(binding.cards),
                "manifest": binding.manifest,
            }, indent=2))
        else:
            print(f"Node: {node_id}")
            if binding.cards:
                print(f"  Matched {len(binding.cards)} cards:")
                for match in binding.manifest.get("matches", []):
                    print(f"    - {match.get('card_id')}: {match.get('title')}")
                    print(f"      Overlap: {match.get('overlap_domains')}")
                    print(f"      Trust: {match.get('trust_level')}")
            else:
                print("  No cards matched.")
            print()

    return 0


def main(argv=None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="mh1 knowledge",
        description="Expert Knowledge Management (Package I3)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add-source
    p_add = subparsers.add_parser("add-source", help="Register a knowledge source file")
    p_add.add_argument("file", help="Path to the source file")
    p_add.add_argument("--title", required=True, help="Title for the source (1-200 chars)")
    p_add.add_argument("--domains", required=True, help="Comma-separated domain tags")
    p_add.add_argument("--format", choices=["markdown", "text", "json"], default="markdown")
    p_add.add_argument("--author", help="Author name")
    p_add.add_argument("--trust-level", choices=["verified", "reviewed", "unreviewed"], default="unreviewed")
    p_add.add_argument("--reviewed-by", help="Reviewer name")
    p_add.add_argument("--valid-until", help="Expiry date (ISO 8601)")
    p_add.add_argument("--allowed-clients", help="Comma-separated client IDs")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Parse sources into knowledge cards")
    p_ingest.add_argument("--source", help="Source ID to ingest")
    p_ingest.add_argument("--all", action="store_true", help="Ingest all active sources")
    p_ingest.add_argument("--force", action="store_true", help="Force re-ingest even if unchanged")
    p_ingest.add_argument("--dry-run", action="store_true", help="Preview without writing")

    # list-cards
    p_cards = subparsers.add_parser("list-cards", help="Show card index")
    p_cards.add_argument("--domain", help="Filter by domain")
    p_cards.add_argument("--type", help="Filter by card type")
    p_cards.add_argument("--json", action="store_true", help="Output as JSON")

    # list-sources
    p_sources = subparsers.add_parser("list-sources", help="Show registered sources")
    p_sources.add_argument("--json", action="store_true", help="Output as JSON")

    # inspect-binding
    p_binding = subparsers.add_parser("inspect-binding", help="Preview binding for a plan")
    p_binding.add_argument("plan", help="Path to plan.json")
    p_binding.add_argument("--node", help="Specific node ID to inspect")
    p_binding.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "add-source": cmd_add_source,
        "ingest": cmd_ingest,
        "list-cards": cmd_list_cards,
        "list-sources": cmd_list_sources,
        "inspect-binding": cmd_inspect_binding,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0
