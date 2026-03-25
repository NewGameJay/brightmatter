#!/usr/bin/env python3
"""One-time historical backfill of all client platform data.

Reads every client's datasources.json, detects configured platforms,
and pulls up to 3 years of historical metrics into Supabase's
client_platform_data table + episodic_memory for BrightMatter learning.

Usage:
    # Full backfill (all clients, all platforms, 3 years)
    python scripts/backfill_platforms.py

    # Filter to a specific client
    python scripts/backfill_platforms.py --client "Mr Christmas"

    # Filter to a specific platform
    python scripts/backfill_platforms.py --platform google_ads

    # Custom lookback
    python scripts/backfill_platforms.py --years 2

    # Dry run (list what would be pulled)
    python scripts/backfill_platforms.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Backfill platform data into BrightMatter")
    parser.add_argument("--client", type=str, default=None, help="Filter to client name (substring match)")
    parser.add_argument("--platform", type=str, default=None, help="Filter to platform (e.g. google_ads)")
    parser.add_argument("--years", type=int, default=3, help="Lookback years (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be pulled without pulling")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("backfill_platforms")

    # Load env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Also load mh1-hq .env for Google/Meta credentials
    mh1_env = os.environ.get("MH1_HQ_ENV", "/Applications/MH1/mh1-hq/.env")
    if os.path.isfile(mh1_env):
        _load_env_file(mh1_env)

    if args.dry_run:
        _dry_run(args)
        return

    logger.info(f"Starting backfill: {args.years} years, client={args.client or 'ALL'}, platform={args.platform or 'ALL'}")

    from lib.platform_ingestion import PlatformDataOrchestrator

    orch = PlatformDataOrchestrator(backfill=True)
    stats = orch.run_backfill(
        lookback_years=args.years,
        client_filter=args.client,
        platform_filter=args.platform,
    )

    logger.info("=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info(f"  Streams pulled:   {stats['streams_pulled']}")
    logger.info(f"  Rows written:     {stats['rows_written']}")
    logger.info(f"  Episodes created: {stats['episodes_created']}")
    if stats.get("errors"):
        logger.warning(f"  Errors:           {len(stats['errors'])}")
        for e in stats["errors"][:10]:
            logger.warning(f"    - {e}")
    logger.info("=" * 60)


def _dry_run(args):
    """List what would be pulled without actually pulling."""
    logging.getLogger().setLevel(logging.WARNING)

    from lib.platform_ingestion.config_resolver import detect_platforms, resolve_config
    from lib.platform_ingestion.orchestrator import PlatformDataOrchestrator, _make_stream_id, _ADAPTERS

    orch = PlatformDataOrchestrator(backfill=True)
    clients = orch._load_clients()

    print(f"\n{'='*70}")
    print(f"  DRY RUN — Platform Data Backfill ({args.years} years)")
    print(f"{'='*70}\n")

    total_streams = 0
    for client in clients:
        if args.client and args.client.lower() not in client["name"].lower():
            continue
        datasources = orch._load_datasources(client["id"])
        if not datasources:
            continue

        platforms = detect_platforms(datasources)
        client_streams = []
        for platform, raw_config in platforms:
            if args.platform and platform != args.platform:
                continue
            if platform not in _ADAPTERS:
                continue
            config = resolve_config(platform, raw_config, client["id"],
                                     client["name"], datasources)
            if not config:
                continue
            stream_id = _make_stream_id(platform, client["name"])
            client_streams.append((platform, stream_id, config.account_id or ""))

        if client_streams:
            print(f"  {client['name']} ({client['id']})")
            for platform, stream_id, acct in client_streams:
                print(f"    -> {stream_id}  (account: {acct[:20]}...)" if len(acct) > 20
                      else f"    -> {stream_id}  (account: {acct})")
                total_streams += 1
            print()

    print(f"  Total streams: {total_streams}")
    print(f"  Lookback: {args.years} years ({args.years * 365} days)")
    print(f"{'='*70}\n")


def _load_env_file(path: str):
    """Load key=value pairs from an env file (skipping comments and complex values)."""
    target_keys = {
        "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "META_ACCESS_TOKEN",
        "SG_META_ACCESS_TOKEN", "HUBSPOT_ACCESS_TOKEN",
    }
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                if key in target_keys and key not in os.environ:
                    os.environ[key] = val.strip()
    except Exception:
        pass


if __name__ == "__main__":
    main()
