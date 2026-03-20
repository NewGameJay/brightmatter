"""
Expert Knowledge (Package I3)

Curated expert knowledge injection for skill execution contexts.
Uploads domain knowledge sources, ingests them into bounded cards,
binds cards to skill nodes via domain overlap, and injects them
as dual-channel context (inline summary + file payload).

This module is additive and disabled by default via feature flags.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Hard caps (non-negotiable bounds) ─────────────────────────────────

MAX_CARD_CONTENT_CHARS = 4000
MAX_CARDS_PER_NODE = 5
MAX_TOTAL_KNOWLEDGE_BYTES = 20_480  # 20KB
MAX_INLINE_SUMMARY_CHARS = 1500
MAX_CITATIONS_PER_CARD = 5
MAX_DOMAINS_PER_CARD = 10
MAX_SOURCE_FILE_BYTES = 512_000  # 500KB hard cap on raw source files
MAX_CITATION_EXCERPT_CHARS = 200

CARD_TYPES = frozenset({
    "definition",
    "checklist",
    "formula",
    "benchmark_table",
    "anti_pattern",
    "example",
})


# ── Configuration ─────────────────────────────────────────────────────

@dataclass
class KnowledgeConfig:
    """
    Configuration for knowledge injection, loaded from plan features.

    Example plan.json features block:
        "features": {
            "knowledge_injection": {
                "enabled": true,
                "max_cards_per_node": 5,
                "inject_strategy": "inline_and_file",
                "allow_unreviewed": false
            }
        }
    """

    enabled: bool = True
    max_cards_per_node: int = MAX_CARDS_PER_NODE
    max_total_bytes: int = MAX_TOTAL_KNOWLEDGE_BYTES
    max_inline_summary_chars: int = MAX_INLINE_SUMMARY_CHARS
    inject_strategy: str = "file_only"  # "file_only" | "inline_and_file"
    allow_unreviewed: bool = False  # Must be explicitly true to bind unreviewed cards

    @classmethod
    def from_features(cls, features: Optional[Dict[str, Any]]) -> "KnowledgeConfig":
        """Load config from plan features dict. Returns disabled config if absent."""
        if not features:
            return cls()
        k_cfg = features.get("knowledge_injection", {})
        if not isinstance(k_cfg, dict):
            return cls()
        return cls(
            enabled=bool(k_cfg.get("enabled", False)),
            max_cards_per_node=int(
                k_cfg.get("max_cards_per_node", MAX_CARDS_PER_NODE)
            ),
            max_total_bytes=int(
                k_cfg.get("max_total_bytes", MAX_TOTAL_KNOWLEDGE_BYTES)
            ),
            max_inline_summary_chars=int(
                k_cfg.get("max_inline_summary_chars", MAX_INLINE_SUMMARY_CHARS)
            ),
            inject_strategy=str(
                k_cfg.get("inject_strategy", "inline_and_file")
            ),
            allow_unreviewed=bool(k_cfg.get("allow_unreviewed", False)),
        )


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class KnowledgeCard:
    """A single knowledge card from the store."""

    card_id: str
    source_id: str
    card_type: str  # one of CARD_TYPES
    title: str
    domains: List[str]
    content: str
    citations: List[Dict[str, str]] = field(default_factory=list)
    trust_level: str = "unreviewed"
    source_version_hash: Optional[str] = None
    created_at: Optional[str] = None
    version: str = "1"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "card_id": self.card_id,
            "source_id": self.source_id,
            "card_type": self.card_type,
            "title": self.title,
            "domains": self.domains,
            "content": self.content,
            "citations": self.citations,
            "trust_level": self.trust_level,
            "version": self.version,
        }
        if self.source_version_hash:
            d["source_version_hash"] = self.source_version_hash
        if self.created_at:
            d["created_at"] = self.created_at
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeCard":
        return cls(
            card_id=data["card_id"],
            source_id=data["source_id"],
            card_type=data.get("card_type", "definition"),
            title=data.get("title", ""),
            domains=data.get("domains", []),
            content=data.get("content", ""),
            citations=data.get("citations", []),
            trust_level=data.get("trust_level", "unreviewed"),
            source_version_hash=data.get("source_version_hash"),
            created_at=data.get("created_at"),
            version=data.get("version", "1"),
        )

    def byte_size(self) -> int:
        """Approximate byte size of this card's content."""
        return len(self.content.encode("utf-8"))


@dataclass
class BindingResult:
    """Result of resolving knowledge cards for a node."""

    cards: List[Dict[str, Any]] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_cards(self) -> bool:
        return len(self.cards) > 0


@dataclass
class KnowledgeInjection:
    """Prepared injection payload for a node."""

    inline_summary: Optional[str] = None
    cards: Optional[List[Dict[str, Any]]] = None
    file_content: Optional[str] = None
    manifest: Optional[Dict[str, Any]] = None

    @property
    def has_content(self) -> bool:
        return self.cards is not None and len(self.cards) > 0
