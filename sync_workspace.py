"""
BrightMatter Workspace Sync

Syncs local BrightMatter source files to the Modal bm-workspace Volume.
Uses content hashing to skip unchanged files.

Usage:
    python sync_workspace.py              # sync all
    python sync_workspace.py --dry-run    # preview changes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Set

import modal

logger = logging.getLogger(__name__)

VOLUME_NAME = "bm-workspace"
PROJECT_ROOT = Path(__file__).parent

SYNC_DIRS = ["lib", "scripts", "schema"]
SYNC_FILES = ["api.py", "worker.py"]

SKIP_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".pyo",
    ".egg-info",
    ".git",
    "node_modules",
    ".env",
    ".DS_Store",
}


def _should_skip(path: Path) -> bool:
    """Check if a path should be excluded from sync."""
    parts = path.parts
    for part in parts:
        for pattern in SKIP_PATTERNS:
            if pattern in part:
                return True
    return False


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's content."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_local_files() -> Dict[str, str]:
    """Collect all files to sync with their content hashes.

    Returns dict mapping relative path -> SHA-256 hash.
    """
    files: Dict[str, str] = {}

    for dir_name in SYNC_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if not dir_path.exists():
            continue
        for file_path in dir_path.rglob("*"):
            if file_path.is_file() and not _should_skip(file_path):
                rel = str(file_path.relative_to(PROJECT_ROOT))
                files[rel] = _file_hash(file_path)

    for file_name in SYNC_FILES:
        file_path = PROJECT_ROOT / file_name
        if file_path.exists():
            files[file_name] = _file_hash(file_path)

    return files


def _load_manifest(vol: modal.Volume) -> Dict[str, str]:
    """Load the sync manifest from the volume."""
    try:
        for entry in vol.read_file(".sync_manifest.json"):
            return json.loads(entry)
    except Exception:
        return {}


def _save_manifest(vol: modal.Volume, manifest: Dict[str, str]):
    """Save the sync manifest to the volume."""
    data = json.dumps(manifest, indent=2).encode()
    vol.write_file(".sync_manifest.json", data)


def sync(dry_run: bool = False) -> Dict[str, int]:
    """Sync local files to the bm-workspace Modal Volume.

    Returns stats: {"uploaded": N, "skipped": N, "removed": N}
    """
    vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
    local_files = _collect_local_files()
    remote_manifest = _load_manifest(vol)

    to_upload: Set[str] = set()
    to_remove: Set[str] = set()

    # Files to upload: new or changed
    for rel_path, local_hash in local_files.items():
        if remote_manifest.get(rel_path) != local_hash:
            to_upload.add(rel_path)

    # Files to remove: in manifest but no longer local
    for rel_path in remote_manifest:
        if rel_path not in local_files:
            to_remove.add(rel_path)

    stats = {
        "uploaded": 0,
        "skipped": len(local_files) - len(to_upload),
        "removed": 0,
    }

    if dry_run:
        if to_upload:
            print(f"Would upload {len(to_upload)} files:")
            for f in sorted(to_upload):
                print(f"  + {f}")
        if to_remove:
            print(f"Would remove {len(to_remove)} files:")
            for f in sorted(to_remove):
                print(f"  - {f}")
        if not to_upload and not to_remove:
            print("Everything up to date.")
        return stats

    # Upload changed files
    for rel_path in sorted(to_upload):
        local_path = PROJECT_ROOT / rel_path
        with open(local_path, "rb") as f:
            vol.write_file(rel_path, f.read())
        stats["uploaded"] += 1
        logger.info(f"Uploaded: {rel_path}")

    # Remove deleted files
    for rel_path in sorted(to_remove):
        try:
            vol.remove_file(rel_path)
            stats["removed"] += 1
            logger.info(f"Removed: {rel_path}")
        except Exception as e:
            logger.debug(f"Could not remove {rel_path}: {e}")

    # Update manifest
    _save_manifest(vol, local_files)
    vol.commit()

    print(
        f"Sync complete: {stats['uploaded']} uploaded, "
        f"{stats['skipped']} unchanged, {stats['removed']} removed"
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync BrightMatter workspace to Modal Volume")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
