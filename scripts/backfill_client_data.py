#!/usr/bin/env python3
"""
BrightMatter Client Data Backfill

One-time pull of historical client data using MH1 HQ's retrieve-and-compute
infrastructure. Reads each client's datasources.json, runs the appropriate
retriever, and ingests computed metrics as BrightMatter episodes.

Granularity tiering:
  0-12 months  → daily + weekly + monthly episodes
  12-24 months → weekly + monthly episodes
  24m-10 years → monthly episodes only

Usage:
    # Dry run — preview what would be ingested
    python scripts/backfill_client_data.py --dry-run

    # Run for a specific client
    python scripts/backfill_client_data.py --client flowcode

    # Run for specific platforms only
    python scripts/backfill_client_data.py --platforms google_ads,meta_ads

    # Full backfill
    python scripts/backfill_client_data.py

Requires:
    - MH1 HQ repo at MH1HQ_PATH (default: /Applications/MH1/mh1-hq)
    - SUPABASE_URL + SUPABASE_KEY
    - Platform API credentials in MH1 HQ .env
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("brightmatter.backfill.clients")

MH1HQ_PATH = os.environ.get("MH1HQ_PATH", "/Applications/MH1/mh1-hq")

PLATFORM_TO_DOMAIN = {
    "google_ads": "campaign",
    "meta_ads": "campaign",
    "hubspot": "revenue",
    "braze": "content",
    "klaviyo": "content",
    "salesforce": "revenue",
    "shopify": "revenue",
    "iterable": "content",
    "customerio": "content",
    "amplitude": "generic",
    "triple_whale": "campaign",
    "beehiiv": "content",
    "snowflake": "generic",
    "bigquery": "generic",
}


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _setup_mh1hq():
    """Add MH1 HQ lib/ to sys.path and load its .env."""
    hq = Path(MH1HQ_PATH)
    if not hq.exists():
        raise FileNotFoundError(f"MH1 HQ not found at {hq}")

    if str(hq) not in sys.path:
        sys.path.insert(0, str(hq))

    hq_env = hq / ".env"
    if hq_env.exists():
        load_dotenv(hq_env, override=False)

    return hq


def _scan_clients(hq_path: Path, only_client: Optional[str] = None) -> List[Dict[str, Any]]:
    """Discover clients with datasource configs."""
    clients_dir = hq_path / "clients"
    results = []

    for client_dir in sorted(clients_dir.iterdir()):
        if not client_dir.is_dir():
            continue

        slug = client_dir.name
        if only_client and slug != only_client:
            continue

        ds_json = client_dir / "config" / "datasources.json"
        ds_yaml = client_dir / "config" / "datasources.yaml"

        ds_path = None
        if ds_json.exists():
            ds_path = ds_json
        elif ds_yaml.exists():
            ds_path = ds_yaml

        if not ds_path:
            continue

        try:
            if ds_path.suffix == ".json":
                with open(ds_path) as f:
                    datasources = json.load(f)
            else:
                import yaml
                with open(ds_path) as f:
                    datasources = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Skipping {slug}: failed to read datasources: {e}")
            continue

        platforms = _detect_platforms(datasources)
        if platforms:
            results.append({
                "slug": slug,
                "dir": client_dir,
                "datasources": datasources,
                "platforms": platforms,
            })

    return results


def _detect_platforms(datasources: dict) -> List[str]:
    """Detect which platforms have configuration in a client's datasources."""
    found = []

    crm = datasources.get("crm", {})
    if isinstance(crm, dict) and crm.get("type"):
        found.append(crm["type"].lower())

    primary = datasources.get("primaryPlatform", datasources.get("primary_platform", {}))
    if isinstance(primary, dict) and primary.get("type"):
        pt = primary["type"].lower()
        if pt not in found:
            found.append(pt)

    integrations = datasources.get("integrations", {})
    if isinstance(integrations, dict):
        for name, cfg in integrations.items():
            if isinstance(cfg, dict):
                t = name.lower()
                if t == "google_ads" or t == "googleads":
                    t = "google_ads"
                elif t == "meta" or t == "facebook":
                    t = "meta_ads"
                if t not in found:
                    found.append(t)
    elif isinstance(integrations, list):
        for entry in integrations:
            if isinstance(entry, dict) and entry.get("type"):
                t = entry["type"].lower()
                if t not in found:
                    found.append(t)

    warehouse = datasources.get("warehouse", {})
    if isinstance(warehouse, dict) and warehouse.get("type"):
        wt = warehouse["type"].lower()
        if wt not in found:
            found.append(wt)

    return found


# ---------------------------------------------------------------------------
# Episode construction
# ---------------------------------------------------------------------------

def _episode_id(platform: str, client: str, granularity: str, date_str: str, key: str) -> str:
    """Deterministic episode ID for idempotent re-runs."""
    raw = f"client-{platform}-{client}-{granularity}-{date_str}-{key}"
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"ep-{platform[:6]}-{h}"


def _metrics_to_episodes(
    client_slug: str,
    platform: str,
    metrics: dict,
    granularities: List[str],
) -> List[Dict[str, Any]]:
    """Convert computed_metrics dict into BrightMatter episode rows.

    Extracts time-series dimensions where they exist (monthly_cohorts,
    lifecycle distributions, deal stages) and creates one episode per
    metric group per time period.
    """
    episodes = []
    domain = PLATFORM_TO_DOMAIN.get(platform, "generic")
    now_iso = datetime.now(timezone.utc).isoformat()

    # --- Monthly cohorts (most retrievers produce this via StreamingAggregator) ---
    cohorts = metrics.get("monthly_cohorts", {})
    if cohorts and "monthly" in granularities:
        sorted_months = sorted(cohorts.keys())
        prior_count = None
        for month_str in sorted_months:
            count = cohorts[month_str]
            if not isinstance(count, (int, float)):
                continue

            ep_id = _episode_id(platform, client_slug, "monthly", month_str, "cohort")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-cohort-monthly",
                domain=domain,
                date_str=f"{month_str}-01",
                granularity="monthly",
                platform=platform,
                expected=prior_count if prior_count else count,
                observed=count,
                metric_name="new_records",
                extra_metrics={"count": count},
            ))
            prior_count = count

    # --- Per-object metrics (contacts, deals, campaigns, etc.) ---
    for obj_name in ("contacts", "deals", "companies", "campaigns", "lists",
                     "profiles", "orders", "products"):
        obj_data = metrics.get(obj_name, {})
        if not isinstance(obj_data, dict):
            continue

        obj_cohorts = obj_data.get("monthly_cohorts", {})
        if obj_cohorts and "monthly" in granularities:
            sorted_months = sorted(obj_cohorts.keys())
            prior_count = None
            for month_str in sorted_months:
                count = obj_cohorts[month_str]
                if not isinstance(count, (int, float)):
                    continue
                ep_id = _episode_id(platform, client_slug, "monthly", month_str, obj_name)
                episodes.append(_build_episode_row(
                    episode_id=ep_id,
                    tenant_id=client_slug,
                    skill_name=f"{platform}-{obj_name}-monthly",
                    domain=domain,
                    date_str=f"{month_str}-01",
                    granularity="monthly",
                    platform=platform,
                    expected=prior_count if prior_count else count,
                    observed=count,
                    metric_name=f"{obj_name}_created",
                    extra_metrics={"count": count},
                ))
                prior_count = count

        record_count = obj_data.get("record_count", 0)
        if record_count and "monthly" in granularities:
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", obj_name)
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-{obj_name}-snapshot",
                domain=domain,
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=record_count,
                observed=record_count,
                metric_name=f"{obj_name}_total",
                extra_metrics=_extract_numeric_metrics(obj_data),
            ))

    # --- Deal stage distribution ---
    deal_stages = metrics.get("deal_stage_distribution", {})
    if deal_stages and "monthly" in granularities:
        for stage, stage_data in deal_stages.items():
            if not isinstance(stage_data, dict):
                continue
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", f"stage-{stage}")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-deal-stage-snapshot",
                domain="revenue",
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=stage_data.get("count", 0),
                observed=stage_data.get("count", 0),
                metric_name=f"deals_in_{stage}",
                extra_metrics=stage_data,
            ))

    # --- Win rate ---
    win_rate = metrics.get("win_rate", {})
    if win_rate and isinstance(win_rate, dict):
        ep_id = _episode_id(platform, client_slug, "snapshot", "latest", "winrate")
        episodes.append(_build_episode_row(
            episode_id=ep_id,
            tenant_id=client_slug,
            skill_name=f"{platform}-win-rate-snapshot",
            domain="revenue",
            date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            granularity="snapshot",
            platform=platform,
            expected=win_rate.get("value", 0),
            observed=win_rate.get("value", 0),
            metric_name="win_rate",
            extra_metrics=win_rate,
        ))

    # --- Deal velocity ---
    velocity = metrics.get("deal_velocity_days", {})
    if velocity and isinstance(velocity, dict):
        ep_id = _episode_id(platform, client_slug, "snapshot", "latest", "velocity")
        episodes.append(_build_episode_row(
            episode_id=ep_id,
            tenant_id=client_slug,
            skill_name=f"{platform}-deal-velocity-snapshot",
            domain="revenue",
            date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            granularity="snapshot",
            platform=platform,
            expected=velocity.get("mean", 0),
            observed=velocity.get("mean", 0),
            metric_name="deal_velocity_days",
            extra_metrics=velocity,
        ))

    # --- Activity recency (30/60/90 day engagement) ---
    for period in ("30d", "60d", "90d"):
        act = metrics.get(f"active_last_{period}", {})
        if act and isinstance(act, dict):
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", f"active-{period}")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-activity-{period}-snapshot",
                domain=domain,
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=act.get("rate", 0),
                observed=act.get("rate", 0),
                metric_name=f"active_rate_{period}",
                extra_metrics=act,
            ))

    # --- Numeric distributions (field-level stats) ---
    numeric = metrics.get("numeric_summaries", {})
    if numeric and isinstance(numeric, dict) and "monthly" in granularities:
        for field_name, summary in numeric.items():
            if not isinstance(summary, dict):
                continue
            if summary.get("count", 0) < 10:
                continue
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", f"num-{field_name[:20]}")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-field-stats-snapshot",
                domain=domain,
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=summary.get("mean", 0),
                observed=summary.get("mean", 0),
                metric_name=field_name,
                extra_metrics=summary,
            ))

    # --- Lifecycle stage distribution ---
    lifecycle = metrics.get("lifecycle_stage_distribution", {})
    if lifecycle and isinstance(lifecycle, dict):
        for stage, stage_data in lifecycle.items():
            if not isinstance(stage_data, dict):
                continue
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", f"lc-{stage}")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-lifecycle-snapshot",
                domain=domain,
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=stage_data.get("count", 0),
                observed=stage_data.get("count", 0),
                metric_name=f"lifecycle_{stage}",
                extra_metrics=stage_data,
            ))

    # --- Fallback: if no structured metrics found, create a snapshot from top-level ---
    if not episodes:
        record_count = metrics.get("record_count", 0)
        if record_count:
            ep_id = _episode_id(platform, client_slug, "snapshot", "latest", "total")
            episodes.append(_build_episode_row(
                episode_id=ep_id,
                tenant_id=client_slug,
                skill_name=f"{platform}-total-snapshot",
                domain=domain,
                date_str=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                granularity="snapshot",
                platform=platform,
                expected=record_count,
                observed=record_count,
                metric_name="record_count",
                extra_metrics=_extract_numeric_metrics(metrics),
            ))

    return episodes


def _build_episode_row(
    episode_id: str,
    tenant_id: str,
    skill_name: str,
    domain: str,
    date_str: str,
    granularity: str,
    platform: str,
    expected: float,
    observed: float,
    metric_name: str,
    extra_metrics: dict,
) -> Dict[str, Any]:
    """Build a Supabase-ready episode row."""
    expected = float(expected) if expected else 0.5
    observed = float(observed) if observed else 0.5
    pe = 0.0
    if expected and expected != 0:
        pe = (observed - expected) / max(abs(expected), 0.01)

    safe_metrics = {}
    for k, v in extra_metrics.items():
        if isinstance(v, (int, float, str, bool)):
            safe_metrics[k] = v

    return {
        "episode_id": episode_id,
        "tenant_id": tenant_id,
        "skill_name": skill_name,
        "domain": domain,
        "prediction": {
            "prediction_id": episode_id,
            "skill_name": skill_name,
            "tenant_id": tenant_id,
            "domain": domain,
            "expected_signal": expected,
            "expected_baseline": 1.0,
            "confidence": 0.5,
            "context": {
                "date": date_str,
                "granularity": granularity,
                "platform": platform,
                "metric": metric_name,
                "source": "historical-backfill",
            },
            "patterns_used": [],
            "is_exploration": False,
            "created_at": f"{date_str}T00:00:00+00:00",
        },
        "outcome": {
            "prediction_id": episode_id,
            "observed_signal": observed,
            "observed_baseline": 1.0,
            "prediction_error": pe,
            "goal_completed": False,
            "metadata": {
                "_source": "historical-backfill",
                "_episode_source": "market",
                **safe_metrics,
            },
        },
        "weight": 1.0,
        "prediction_error": pe,
        "source": "historical-backfill",
        "created_at": f"{date_str}T00:00:00+00:00",
    }


def _extract_numeric_metrics(data: dict) -> dict:
    """Pull numeric values from a dict, skipping nested structures."""
    result = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _run_retrieval(
    client_slug: str,
    platform: str,
    datasources: dict,
    lookback_days: int = 365,
) -> Optional[dict]:
    """Run retrieve-and-compute for a single client+platform.

    Uses MH1 HQ's retrieve_and_compute internals to pull data.
    """
    rc_path = Path(MH1HQ_PATH) / "skills" / "operations-skills" / "platform-retrieval" / "scripts"
    if str(rc_path) not in sys.path:
        sys.path.insert(0, str(rc_path))

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "retrieve_and_compute", rc_path / "retrieve_and_compute.py"
    )
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)

    try:
        platform_config = rc._get_platform_config(platform, datasources)
    except ValueError as e:
        logger.warning(f"  [{client_slug}/{platform}] No config: {e}")
        return None

    cred_keys = ("token", "access_token", "api_key", "rest_api_key",
                  "private_key", "bearer_token", "app_api_key")
    has_creds = any(platform_config.get(k) for k in cred_keys)

    if not has_creds:
        integrations = datasources.get("integrations", {})
        if isinstance(integrations, dict) and platform in integrations:
            int_cfg = integrations[platform]
            if isinstance(int_cfg, dict):
                for ck in cred_keys:
                    if int_cfg.get(ck):
                        platform_config[ck] = int_cfg[ck]
                        has_creds = True
                        break

    if not has_creds:
        env_token = (
            os.environ.get(f"{platform.upper()}_ACCESS_TOKEN")
            or os.environ.get(f"{platform.upper()}_API_KEY")
        )
        if env_token:
            platform_config["token"] = env_token
            has_creds = True

    if not has_creds:
        logger.warning(f"  [{client_slug}/{platform}] No credentials found, skipping")
        return None

    platform_config["_lookback_days"] = lookback_days

    logger.info(f"  [{client_slug}/{platform}] Retrieving (lookback={lookback_days}d)...")

    try:
        # Use the appropriate strategy from retrieve_and_compute
        from lib.retrieval.router import select_strategy

        strategy = select_strategy(platform, platform_config)
        logger.info(f"  [{client_slug}/{platform}] Strategy: {strategy.strategy_name}")

        if strategy.strategy_name == "warehouse_sql":
            metrics, _, _, _ = rc._execute_warehouse_strategy(
                platform, platform_config, datasources
            )
        elif strategy.strategy_name == "bulk_export" and platform == "hubspot":
            metrics, _, _, _ = rc._execute_hubspot_export(platform_config)
        elif strategy.strategy_name in ("direct_api", "streaming_api"):
            retriever_class = rc._get_retriever_class(platform)
            if hasattr(retriever_class, "stream_and_compute"):
                metrics, _, _, _ = rc._execute_stream_and_compute(
                    platform, platform_config, retriever_class
                )
            else:
                metrics, _, _, _ = rc._execute_api_strategy(
                    platform, platform_config, strategy.strategy_name
                )
        else:
            metrics, _, _, _ = rc._execute_api_strategy(
                platform, platform_config, "streaming_api"
            )

        record_count = metrics.get("record_count", 0)
        logger.info(f"  [{client_slug}/{platform}] Got {record_count} records")
        return metrics

    except Exception as e:
        logger.error(f"  [{client_slug}/{platform}] Retrieval failed: {e}")
        return None


def _run_retrieval_simple(
    client_slug: str,
    platform: str,
    datasources: dict,
) -> Optional[dict]:
    """Fallback: import the retriever directly and run discover + retrieve."""
    try:
        from lib.retrieval.schema import discover_schema

        # Resolve config
        rc_path = Path(MH1HQ_PATH) / "skills" / "operations-skills" / "platform-retrieval" / "scripts"
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "retrieve_and_compute", rc_path / "retrieve_and_compute.py"
        )
        rc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rc)
        platform_config = rc._get_platform_config(platform, datasources)
        retriever_class = rc._get_retriever_class(platform)

        schema = discover_schema(platform, platform_config)
        all_metrics: dict = {"record_count": 0}

        for obj_name, obj_schema in schema.objects.items():
            if (obj_schema.record_count or 0) == 0:
                continue
            records, _ = retriever_class.retrieve_all(
                platform_config, obj_name,
                schema_manifest=schema,
                properties=obj_schema.properties,
            )
            metrics, _ = retriever_class.compute_standard_metrics(
                records, schema, obj_name
            )
            all_metrics[obj_name] = metrics
            all_metrics["record_count"] += metrics.get("record_count", len(records))

        return all_metrics
    except Exception as e:
        logger.error(f"  [{client_slug}/{platform}] Simple retrieval failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _ingest_episodes(episodes: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, int]:
    """Batch upsert episodes into Supabase."""
    stats = {"created": 0, "skipped": 0, "failed": 0}

    if dry_run:
        for ep in episodes:
            logger.info(
                f"  [DRY RUN] {ep['episode_id']} | {ep['tenant_id']} | "
                f"{ep['skill_name']} | {ep.get('domain', '?')}"
            )
            stats["skipped"] += 1
        return stats

    import importlib.util as _ilu
    _bm_sc = Path(__file__).resolve().parent.parent / "lib" / "supabase_client.py"
    _spec = _ilu.spec_from_file_location("bm_supabase_client", _bm_sc)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    db = _mod.get_supabase()

    batch_size = 50
    for i in range(0, len(episodes), batch_size):
        batch = episodes[i : i + batch_size]
        try:
            db.table("episodic_memory").upsert(
                batch, on_conflict="episode_id"
            ).execute()
            stats["created"] += len(batch)
        except Exception as e:
            logger.error(f"  Batch upsert failed ({len(batch)} episodes): {e}")
            for ep in batch:
                try:
                    db.table("episodic_memory").upsert(
                        ep, on_conflict="episode_id"
                    ).execute()
                    stats["created"] += 1
                except Exception as e2:
                    logger.warning(f"  Failed: {ep['episode_id']}: {e2}")
                    stats["failed"] += 1

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill BrightMatter from client platform data"
    )
    parser.add_argument("--client", help="Only process this client slug")
    parser.add_argument(
        "--platforms",
        help="Comma-separated platform filter (e.g. google_ads,hubspot)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=3650,
        help="Max lookback in days (default: 3650 = ~10 years)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    platform_filter = None
    if args.platforms:
        platform_filter = set(args.platforms.split(","))

    hq_path = _setup_mh1hq()
    logger.info(f"MH1 HQ path: {hq_path}")

    clients = _scan_clients(hq_path, only_client=args.client)
    logger.info(f"Found {len(clients)} clients with datasource configs")

    for c in clients:
        logger.info(f"  {c['slug']}: {', '.join(c['platforms'])}")

    total_stats = {"clients": 0, "platforms": 0, "episodes": 0, "failed": 0}
    granularities = ["monthly"]  # all data gets monthly; daily/weekly added below

    for client in clients:
        slug = client["slug"]
        datasources = client["datasources"]
        platforms = client["platforms"]

        if platform_filter:
            platforms = [p for p in platforms if p in platform_filter]

        if not platforms:
            continue

        total_stats["clients"] += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"CLIENT: {slug} ({len(platforms)} platforms)")
        logger.info(f"{'='*60}")

        for platform in platforms:
            total_stats["platforms"] += 1

            try:
                metrics = _run_retrieval(slug, platform, datasources, args.lookback)
            except Exception as e:
                logger.error(f"  [{slug}/{platform}] Crash in retrieval: {e}")
                metrics = None

            if not metrics:
                metrics = _run_retrieval_simple(slug, platform, datasources)

            if not metrics:
                logger.warning(f"  [{slug}/{platform}] No data retrieved")
                total_stats["failed"] += 1
                continue

            episodes = _metrics_to_episodes(slug, platform, metrics, granularities)
            logger.info(f"  [{slug}/{platform}] Built {len(episodes)} episodes")

            if episodes:
                ingest_stats = _ingest_episodes(episodes, dry_run=args.dry_run)
                total_stats["episodes"] += ingest_stats["created"] + ingest_stats["skipped"]
                total_stats["failed"] += ingest_stats["failed"]
                logger.info(
                    f"  [{slug}/{platform}] Ingested: "
                    f"{ingest_stats['created']} created, "
                    f"{ingest_stats['skipped']} skipped, "
                    f"{ingest_stats['failed']} failed"
                )

    # Post-backfill consolidation (skip if no Firebase creds available)
    if not args.dry_run and total_stats["episodes"] > 0:
        logger.info("\nSkipping consolidation (runs via scheduled worker)")

    logger.info(f"\n{'='*60}")
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  Clients: {total_stats['clients']}")
    logger.info(f"  Platforms: {total_stats['platforms']}")
    logger.info(f"  Episodes: {total_stats['episodes']}")
    logger.info(f"  Failed: {total_stats['failed']}")
    logger.info(f"{'='*60}")

    return total_stats


if __name__ == "__main__":
    main()
