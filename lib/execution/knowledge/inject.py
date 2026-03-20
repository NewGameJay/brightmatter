"""
Expert Knowledge — Injection Layer (Package I3)

Orchestrates knowledge binding and prepares dual-channel injection
payload for skill execution contexts:

  Channel A (Inline): Bounded metadata summary in context_slice
  Channel B (File):   Full knowledge_cards.json in sandbox
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.execution.knowledge import (
    KnowledgeConfig,
    KnowledgeInjection,
    MAX_INLINE_SUMMARY_CHARS,
)
from lib.execution.knowledge.bind import resolve_cards_for_node


def _build_inline_summary(
    cards: List[Dict[str, Any]],
    max_chars: int = MAX_INLINE_SUMMARY_CHARS,
) -> str:
    """
    Build Channel A inline summary — metadata only, never raw content.

    Format:
        ## Expert Knowledge (N cards matched)
        - [card_type] Title (domains: d1, d2) [trust_level]
        ...
        Use read_file("knowledge_cards.json") for full card contents.

    Args:
        cards: List of matched card dicts.
        max_chars: Maximum summary length.

    Returns:
        Bounded summary string.
    """
    if not cards:
        return ""

    lines = [f"## Expert Knowledge ({len(cards)} cards matched)"]

    for card in cards:
        card_type = card.get("card_type", "definition")
        title = card.get("title", "Untitled")
        domains = ", ".join(card.get("domains", []))
        trust = card.get("trust_level", "unreviewed")

        tag = f" [UNREVIEWED]" if trust == "unreviewed" else f" [{trust}]"
        line = f"- [{card_type}] {title} (domains: {domains}){tag}"
        lines.append(line)

    lines.append('Use read_file("knowledge_cards.json") for full card contents.')

    summary = "\n".join(lines)

    # Truncate if exceeds max
    if len(summary) > max_chars:
        # Truncate at a line boundary
        truncated = summary[:max_chars]
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        truncated += "\n... (truncated)"
        return truncated

    return summary


def _build_file_payload(
    cards: List[Dict[str, Any]],
    node_id: str,
    manifest: Dict[str, Any],
) -> str:
    """
    Build Channel B file payload — full knowledge_cards.json content.

    Args:
        cards: List of matched card dicts.
        node_id: Node ID for reference.
        manifest: Binding manifest for audit.

    Returns:
        JSON string of the payload.
    """
    payload = {
        "version": "1",
        "node_id": node_id,
        "cards": cards,
        "manifest": manifest,
    }
    return json.dumps(payload, indent=2)


def prepare_knowledge_injection(
    project_root: str,
    node_config: Dict[str, Any],
    config: KnowledgeConfig,
    skill_meta: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    client_id: Optional[str] = None,
    store_dir: Optional[str] = None,
) -> KnowledgeInjection:
    """
    Prepare knowledge injection payload for a node.

    Orchestrates: load index -> resolve binding -> build inline summary
    + file payload.

    Args:
        project_root: Path to project root.
        node_config: Node configuration dict.
        config: KnowledgeConfig instance.
        skill_meta: Optional skill metadata from skills_index.json.
        agent_meta: Optional agent metadata.
        client_id: Optional client ID for client-scoped filtering.
        store_dir: Optional override for knowledge_store directory.

    Returns:
        KnowledgeInjection with inline_summary, cards, file_content, manifest.
    """
    injection = KnowledgeInjection()

    if not config.enabled:
        return injection

    # Determine store paths
    root = Path(project_root)
    if store_dir:
        store_root = Path(store_dir)
    else:
        store_root = root / "knowledge_store"

    cards_index_path = str(store_root / "cards_index.json")
    cards_dir = str(store_root / "cards")

    if not Path(cards_index_path).exists():
        return injection

    # Resolve binding
    binding = resolve_cards_for_node(
        node_config=node_config,
        cards_index_path=cards_index_path,
        cards_dir=cards_dir,
        config=config,
        skill_meta=skill_meta,
        agent_meta=agent_meta,
        client_id=client_id,
    )

    if not binding.has_cards:
        return injection

    node_id = node_config.get("node_id", "unknown")

    # Build Channel A: inline summary (metadata only)
    if config.inject_strategy in ("inline_and_file",):
        injection.inline_summary = _build_inline_summary(
            binding.cards,
            max_chars=config.max_inline_summary_chars,
        )

    # Build Channel B: file payload
    injection.file_content = _build_file_payload(
        binding.cards,
        node_id,
        binding.manifest,
    )

    injection.cards = binding.cards
    injection.manifest = binding.manifest

    return injection
