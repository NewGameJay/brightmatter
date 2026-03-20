"""
Expert Knowledge — Storage Layer (Package I3)

Filesystem-backed storage for knowledge sources and cards.
Provides CRUD operations, hash-based change detection,
re-ingest support, and index management.
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.execution.evidence.hash_utils import compute_sha256
from lib.execution.knowledge import (
    MAX_SOURCE_FILE_BYTES,
)


def _slugify(text: str, max_len: int = 12) -> str:
    """Convert text to URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    slug = slug.strip("-")
    return slug[:max_len]


class KnowledgeStore:
    """
    Filesystem-backed knowledge store.

    Directory structure:
        knowledge_store/
          sources.json              # Array of source metadata
          raw/                      # Raw uploaded files by source_id
          cards/                    # Individual card JSON files: {card_id}.json
          cards_index.json          # Flat index: {"version": "1", "cards": [...]}
    """

    def __init__(self, store_dir: Optional[str] = None):
        if store_dir:
            self._root = Path(store_dir)
        else:
            self._root = Path("knowledge_store")
        self._sources_path = self._root / "sources.json"
        self._raw_dir = self._root / "raw"
        self._cards_dir = self._root / "cards"
        self._index_path = self._root / "cards_index.json"

    def _ensure_dirs(self) -> None:
        """Create store directories if they don't exist."""
        self._root.mkdir(parents=True, exist_ok=True)
        self._raw_dir.mkdir(exist_ok=True)
        self._cards_dir.mkdir(exist_ok=True)
        if not self._sources_path.exists():
            self._sources_path.write_text("[]")
        if not self._index_path.exists():
            self._index_path.write_text(json.dumps({"version": "1", "cards": []}))

    # ── Sources ───────────────────────────────────────────────────────

    def _load_sources(self) -> List[Dict[str, Any]]:
        """Load sources list from disk."""
        if not self._sources_path.exists():
            return []
        try:
            data = json.loads(self._sources_path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_sources(self, sources: List[Dict[str, Any]]) -> None:
        """Write sources list to disk."""
        self._ensure_dirs()
        self._sources_path.write_text(json.dumps(sources, indent=2))

    def add_source(
        self,
        file_path: str,
        title: str,
        domains: List[str],
        format: str = "markdown",
        author: str = "unknown",
        trust_level: str = "unreviewed",
        reviewed_by: Optional[str] = None,
        valid_until: Optional[str] = None,
        allowed_clients: Optional[List[str]] = None,
    ) -> str:
        """
        Register a knowledge source.

        Copies raw file to knowledge_store/raw/, computes SHA-256,
        appends metadata to sources.json.

        Args:
            file_path: Path to the source file to register.
            title: Human-readable title (1-200 chars).
            domains: Domain tags (1-10 items).
            format: File format (markdown|text|json).
            author: Author name.
            trust_level: Trust level (verified|reviewed|unreviewed).
            reviewed_by: Reviewer name or None.
            valid_until: ISO date-time for expiry or None.
            allowed_clients: Client IDs or None for all.

        Returns:
            source_id of the registered source.

        Raises:
            ValueError: If file is too large, missing, or title/domains invalid.
        """
        self._ensure_dirs()

        source_file = Path(file_path)
        if not source_file.exists():
            raise ValueError(f"Source file not found: {file_path}")

        file_size = source_file.stat().st_size
        if file_size > MAX_SOURCE_FILE_BYTES:
            raise ValueError(
                f"Source file exceeds {MAX_SOURCE_FILE_BYTES} bytes limit: "
                f"{file_size} bytes"
            )

        if not title or len(title) > 200:
            raise ValueError("Title must be 1-200 characters")

        if not domains or len(domains) > 10:
            raise ValueError("Domains must have 1-10 items")

        if format not in ("markdown", "text", "json"):
            raise ValueError(f"Invalid format: {format}. Must be markdown, text, or json")

        # Generate source_id from title slug
        slug = _slugify(title)
        source_id = f"src-{slug}"

        # Ensure uniqueness
        sources = self._load_sources()
        existing_ids = {s["source_id"] for s in sources}
        if source_id in existing_ids:
            # Append counter
            counter = 2
            while f"{source_id}-{counter}" in existing_ids:
                counter += 1
            source_id = f"{source_id}-{counter}"
            # Ensure still within pattern
            if len(source_id) > 16:  # src- + 12
                source_id = source_id[:16]

        # Copy raw file
        raw_dest = self._raw_dir / f"{source_id}{source_file.suffix}"
        shutil.copy2(str(source_file), str(raw_dest))

        # Compute hash
        version_hash = compute_sha256(raw_dest)

        now = datetime.now(timezone.utc).isoformat()

        source_meta = {
            "source_id": source_id,
            "title": title,
            "domains": [d.lower().strip() for d in domains],
            "file_path": str(raw_dest.relative_to(self._root)),
            "format": format,
            "created_at": now,
            "updated_at": now,
            "version_hash": version_hash,
            "status": "active",
            "author": author,
            "reviewed_by": reviewed_by,
            "trust_level": trust_level,
            "valid_until": valid_until,
            "allowed_clients": allowed_clients,
        }

        sources.append(source_meta)
        self._save_sources(sources)

        return source_id

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get source metadata by ID. Returns None if not found."""
        sources = self._load_sources()
        for s in sources:
            if s["source_id"] == source_id:
                return s
        return None

    def list_sources(self, status: str = "active") -> List[Dict[str, Any]]:
        """List sources filtered by status."""
        sources = self._load_sources()
        return [s for s in sources if s.get("status", "active") == status]

    def archive_source(self, source_id: str) -> bool:
        """Soft-delete a source by setting status to 'archived'."""
        sources = self._load_sources()
        for s in sources:
            if s["source_id"] == source_id:
                s["status"] = "archived"
                s["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save_sources(sources)
                return True
        return False

    def get_expired_sources(self) -> List[Dict[str, Any]]:
        """Return sources where valid_until is past current date."""
        now = datetime.now(timezone.utc)
        sources = self._load_sources()
        expired = []
        for s in sources:
            if s.get("status") != "active":
                continue
            valid_until = s.get("valid_until")
            if valid_until:
                try:
                    expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                    if expiry < now:
                        expired.append(s)
                except (ValueError, TypeError):
                    pass
        return expired

    # ── Cards ─────────────────────────────────────────────────────────

    def write_card(self, card: Dict[str, Any]) -> str:
        """
        Write a knowledge card to disk.

        Args:
            card: Card dict conforming to knowledge_card schema.

        Returns:
            card_id of the written card.
        """
        self._ensure_dirs()
        card_id = card["card_id"]
        card_path = self._cards_dir / f"{card_id}.json"
        card_path.write_text(json.dumps(card, indent=2))

        # Update index
        self._add_to_index(card)

        return card_id

    def read_card(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Read a card by ID from disk."""
        card_path = self._cards_dir / f"{card_id}.json"
        if not card_path.exists():
            return None
        try:
            return json.loads(card_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def list_cards(
        self,
        domain: Optional[str] = None,
        card_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List cards from the index, with optional filtering.

        Args:
            domain: Filter by domain (case-insensitive).
            card_type: Filter by card_type.

        Returns:
            List of card metadata dicts from the index.
        """
        index = self._load_index()
        cards = index.get("cards", [])

        if domain:
            domain_lower = domain.lower()
            cards = [
                c for c in cards
                if domain_lower in [d.lower() for d in c.get("domains", [])]
            ]

        if card_type:
            cards = [c for c in cards if c.get("card_type") == card_type]

        return cards

    def rebuild_index(self) -> int:
        """
        Rebuild cards_index.json by scanning cards/ directory.

        Returns:
            Number of cards indexed.
        """
        self._ensure_dirs()
        cards = []
        for card_file in sorted(self._cards_dir.glob("kc-*.json")):
            try:
                card_data = json.loads(card_file.read_text())
                cards.append(card_data)
            except (json.JSONDecodeError, OSError):
                continue

        index = {"version": "1", "cards": cards}
        self._index_path.write_text(json.dumps(index, indent=2))
        return len(cards)

    def detect_source_changes(self, source_id: str) -> bool:
        """
        Check if raw source file has changed since last ingest.

        Returns:
            True if source has changed, False if unchanged.
        """
        source = self.get_source(source_id)
        if not source:
            return True  # Not found = treat as changed

        raw_path = self._root / source["file_path"]
        if not raw_path.exists():
            return True

        current_hash = compute_sha256(raw_path)
        return current_hash != source.get("version_hash")

    def purge_cards_for_source(self, source_id: str) -> int:
        """
        Remove all cards from a source.

        Returns:
            Number of cards removed.
        """
        index = self._load_index()
        original_count = len(index.get("cards", []))
        remaining = [
            c for c in index.get("cards", [])
            if c.get("source_id") != source_id
        ]
        removed_count = original_count - len(remaining)

        # Delete card files
        for card_file in self._cards_dir.glob("kc-*.json"):
            try:
                card_data = json.loads(card_file.read_text())
                if card_data.get("source_id") == source_id:
                    card_file.unlink()
            except (json.JSONDecodeError, OSError):
                continue

        # Update index
        index["cards"] = remaining
        self._index_path.write_text(json.dumps(index, indent=2))

        return removed_count

    def get_raw_path(self, source_id: str) -> Optional[Path]:
        """Get the raw file path for a source."""
        source = self.get_source(source_id)
        if not source:
            return None
        raw_path = self._root / source["file_path"]
        return raw_path if raw_path.exists() else None

    # ── Index helpers ─────────────────────────────────────────────────

    def _load_index(self) -> Dict[str, Any]:
        """Load cards index from disk."""
        if not self._index_path.exists():
            return {"version": "1", "cards": []}
        try:
            data = json.loads(self._index_path.read_text())
            return data if isinstance(data, dict) else {"version": "1", "cards": []}
        except (json.JSONDecodeError, OSError):
            return {"version": "1", "cards": []}

    def _add_to_index(self, card: Dict[str, Any]) -> None:
        """Add or update a card in the index."""
        index = self._load_index()
        cards = index.get("cards", [])

        # Replace if exists
        cards = [c for c in cards if c.get("card_id") != card["card_id"]]
        cards.append(card)

        index["cards"] = cards
        self._index_path.write_text(json.dumps(index, indent=2))

    @property
    def cards_index_path(self) -> Path:
        """Path to the cards index file."""
        return self._index_path

    @property
    def cards_dir(self) -> Path:
        """Path to the cards directory."""
        return self._cards_dir

    @property
    def root(self) -> Path:
        """Path to the store root directory."""
        return self._root
