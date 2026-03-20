"""
Backfill orchestration for memory ingestion.

Discovers historical runs and produces ingestion bundles for each.
Always uses warn mode (disk-only, no Firebase writes).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import MemoryIngestionConfig
from .collect import collect_artifacts
from .bundle import assemble_bundle, write_bundle, write_report

logger = logging.getLogger(__name__)


def discover_runs(
    client_id: str,
    since: Optional[str],
    project_root: Path,
) -> List[Path]:
    """
    Find run directories for a client, newest first.

    1. Try run_index.jsonl (I1) if present — fast path
    2. Fall back to walking modules/*/runs/*/state.json — slow but universal
    """
    runs: List[Path] = []
    since_dt = None
    if since:
        try:
            raw = since.replace("Z", "+00:00")
            since_dt = datetime.fromisoformat(raw)
            # Make timezone-naive dates comparable (treat as UTC midnight)
            if since_dt.tzinfo is None:
                from datetime import timezone as tz
                since_dt = since_dt.replace(tzinfo=tz.utc)
        except (ValueError, TypeError):
            logger.warning("Invalid --since date: %s, ignoring filter", since)

    # Fast path: run_index.jsonl
    index_path = project_root / "run_index.jsonl"
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("client_id") != client_id:
                        continue
                    run_dir_str = entry.get("run_dir")
                    if not run_dir_str:
                        continue
                    run_dir = Path(run_dir_str)
                    if not run_dir.is_absolute():
                        run_dir = project_root / run_dir
                    if not run_dir.is_dir():
                        continue
                    # Date filter
                    if since_dt:
                        created = entry.get("created_at", "")
                        if created:
                            try:
                                run_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                if run_dt < since_dt:
                                    continue
                            except (ValueError, TypeError):
                                pass
                    runs.append(run_dir)
            if runs:
                return sorted(runs, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        except Exception as e:
            logger.warning("run_index.jsonl read failed, falling back to directory walk: %s", e)

    # Slow path: walk clients/*/modules/*/runs/*/state.json
    clients_dir = project_root / "clients"
    if not clients_dir.is_dir():
        return []

    all_module_dirs = []
    for client_dir in sorted(clients_dir.iterdir()):
        if not client_dir.is_dir():
            continue
        mods_dir = client_dir / "modules"
        if mods_dir.is_dir():
            for mod in sorted(mods_dir.iterdir()):
                if mod.is_dir():
                    all_module_dirs.append(mod)

    for module_dir in all_module_dirs:
        runs_dir = module_dir / "runs"
        if not runs_dir.is_dir():
            continue
        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            state_path = run_dir / "state.json"
            if not state_path.exists():
                continue
            try:
                state = json.loads(state_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if state.get("client_id") != client_id:
                continue
            # Date filter
            if since_dt:
                created = state.get("created_at", "")
                if created:
                    try:
                        run_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if run_dt < since_dt:
                            continue
                    except (ValueError, TypeError):
                        pass
            runs.append(run_dir)

    return runs


def backfill_runs(
    client_id: str,
    since: Optional[str],
    project_root: Path,
    limit: Optional[int] = None,
    dry_run: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Backfill memory ingestion for historical runs.

    Args:
        client_id: Client ID to filter runs
        since: ISO date string — only process runs created on/after this date
        project_root: Root of the MH1 project
        limit: Max runs to process (None = unlimited)
        dry_run: If True, print what would be done but write nothing
        force: If True, re-ingest runs that already have a bundle

    Returns:
        Summary dict with counts and errors
    """
    runs = discover_runs(client_id, since, project_root)
    if limit and limit > 0:
        runs = runs[:limit]

    # Always use warn mode — no Firebase writes during backfill
    config = MemoryIngestionConfig(enabled=True, mode="warn", include_failed=False)

    summary = {
        "client_id": client_id,
        "since": since,
        "runs_found": len(runs),
        "runs_processed": 0,
        "runs_skipped_existing": 0,
        "runs_skipped_error": 0,
        "errors": [],
    }

    for run_dir in runs:
        run_id = run_dir.name
        bundle_path = run_dir / "memory" / "ingestion_bundle.json"

        # Idempotency check
        if bundle_path.exists() and not force:
            summary["runs_skipped_existing"] += 1
            if dry_run:
                print(f"  [skip] {run_id} — bundle exists (use --force to re-ingest)")
            continue

        if dry_run:
            print(f"  [dry-run] {run_id} — would ingest from {run_dir}")
            summary["runs_processed"] += 1
            continue

        # Ingest
        try:
            artifacts = collect_artifacts(run_dir, config)
            if artifacts is None:
                summary["runs_skipped_error"] += 1
                summary["errors"].append(f"{run_id}: state.json missing or unreadable")
                continue

            bundle, report = assemble_bundle(artifacts, config)
            write_bundle(bundle, run_dir)
            write_report(report, run_dir)
            summary["runs_processed"] += 1
            print(f"  [ok] {run_id} — {bundle['entry_count']} entries")

        except Exception as e:
            summary["runs_skipped_error"] += 1
            summary["errors"].append(f"{run_id}: {e}")
            print(f"  [error] {run_id} — {e}")

    return summary
