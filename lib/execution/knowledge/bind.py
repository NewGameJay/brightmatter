"""
Expert Knowledge — Binding Resolver (Package I3)

Deterministic domain-overlap binding between knowledge cards and skill nodes.
Computed at execution time (not plan time), never persisted.
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lib.execution.knowledge import (
    BindingResult,
    KnowledgeConfig,
    MAX_CARDS_PER_NODE,
    MAX_TOTAL_KNOWLEDGE_BYTES,
)


# ── Domain Normalization ──────────────────────────────────────────────

def _normalize_domains(raw_terms: List[str]) -> Set[str]:
    """
    Normalize domain terms to lowercase tokens, splitting hyphens.

    'customer-intelligence' -> {'customer', 'intelligence'}
    'Email' -> {'email'}
    """
    tokens = set()
    for term in raw_terms:
        # Lowercase and strip
        term_lower = term.lower().strip()
        # Split on hyphens to get individual tokens
        parts = term_lower.split("-")
        for part in parts:
            part = part.strip()
            if part:
                tokens.add(part)
        # Also keep the compound form
        if term_lower:
            tokens.add(term_lower)
    return tokens


def _extract_node_domains(
    node_config: Dict[str, Any],
    skill_meta: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    """
    Build the domain set for a node from skill tags, category, and agent capabilities.

    Sources:
      - skill_meta: tags[] + category from skills_index.json
      - agent_meta: keywords from capabilities[] in AGENT.md frontmatter, plus skills[] list
      - node_config: skill_name, node_type
    """
    raw_terms: List[str] = []

    # From skill metadata (skills_index.json entry)
    if skill_meta:
        raw_terms.extend(skill_meta.get("tags", []))
        category = skill_meta.get("category", "")
        if category:
            raw_terms.append(category)

    # From agent metadata
    if agent_meta:
        raw_terms.extend(agent_meta.get("capabilities", []))
        raw_terms.extend(agent_meta.get("skills", []))

    # From node config (fallback)
    skill_name = node_config.get("skill_name", "")
    if skill_name:
        # Split skill name into tokens: 'lifecycle-audit' -> ['lifecycle', 'audit']
        raw_terms.extend(skill_name.replace("-", " ").split())

    node_type = node_config.get("node_type", "")
    if node_type:
        raw_terms.append(node_type)

    return _normalize_domains(raw_terms)


# ── Card Filtering ────────────────────────────────────────────────────

def _is_card_expired(card: Dict[str, Any]) -> bool:
    """Check if a card is expired based on source valid_until or 90-day auto-expiry."""
    now = datetime.now(timezone.utc)
    trust_level = card.get("trust_level", "unreviewed")
    valid_until = card.get("valid_until")

    if valid_until:
        try:
            expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            return expiry < now
        except (ValueError, TypeError):
            pass

    # Unreviewed cards with no valid_until auto-expire after 90 days
    if trust_level == "unreviewed":
        created_at = card.get("created_at")
        if created_at:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                return (now - created) > timedelta(days=90)
            except (ValueError, TypeError):
                pass
        # If no created_at, treat as expired for safety
        return True

    return False


def _filter_card(
    card: Dict[str, Any],
    config: KnowledgeConfig,
    client_id: Optional[str] = None,
) -> Optional[str]:
    """
    Check if a card should be filtered out.

    Returns:
        None if card passes all filters, or a string reason for filtering.
    """
    trust_level = card.get("trust_level", "unreviewed")

    # Filter unreviewed cards (unless explicitly allowed)
    if trust_level == "unreviewed" and not config.allow_unreviewed:
        return "unreviewed"

    # Filter expired cards
    if _is_card_expired(card):
        return "expired"

    # Filter by allowed_clients (strictly enforced)
    allowed_clients = card.get("allowed_clients")
    if allowed_clients is not None and client_id:
        if client_id not in allowed_clients:
            return f"client_not_allowed:{client_id}"
    elif allowed_clients is not None and not client_id:
        # If card has client restriction but we don't know the client, exclude
        return "client_unknown"

    return None


# ── Main Binding Function ────────────────────────────────────────────

def resolve_cards_for_node(
    node_config: Dict[str, Any],
    cards_index_path: str,
    cards_dir: str,
    config: KnowledgeConfig,
    skill_meta: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    client_id: Optional[str] = None,
) -> BindingResult:
    """
    Resolve knowledge cards for a node via deterministic domain-overlap.

    Algorithm:
    1. Build node domain set from skill tags + category + agent capabilities
    2. For each card: compute domain overlap
    3. Filter by trust/expiry/client
    4. Primary selection: overlap >= 2
    5. Backfill: overlap == 1 if primary < max_cards
    6. Sort: overlap DESC, card_id ASC (deterministic tie-breaker)
    7. Cap at max_cards_per_node (default 5)
    8. Enforce byte budget (20KB)

    Args:
        node_config: Node configuration dict with skill_name, node_type, etc.
        cards_index_path: Path to cards_index.json.
        cards_dir: Path to cards/ directory.
        config: KnowledgeConfig instance.
        skill_meta: Optional skill metadata from skills_index.json.
        agent_meta: Optional agent metadata.
        client_id: Optional client ID for client-scoped filtering.

    Returns:
        BindingResult with matched cards and manifest.
    """
    result = BindingResult()

    # Load cards index
    index_path = Path(cards_index_path)
    if not index_path.exists():
        return result

    try:
        index_data = json.loads(index_path.read_text())
        all_cards = index_data.get("cards", [])
    except (json.JSONDecodeError, OSError):
        return result

    if not all_cards:
        return result

    # Build node domain set
    node_domains = _extract_node_domains(node_config, skill_meta, agent_meta)
    if not node_domains:
        return result

    # Score each card by domain overlap
    scored_cards: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for card in all_cards:
        # Apply filters
        filter_reason = _filter_card(card, config, client_id)
        if filter_reason:
            skipped.append({
                "card_id": card.get("card_id", "unknown"),
                "reason": filter_reason,
            })
            continue

        # Compute domain overlap
        card_domains = _normalize_domains(card.get("domains", []))
        overlap = len(card_domains & node_domains)

        if overlap > 0:
            scored_cards.append({
                **card,
                "_overlap": overlap,
            })

    # Separate primary (overlap >= 2) and backfill (overlap == 1)
    max_cards = config.max_cards_per_node or MAX_CARDS_PER_NODE
    primary = [c for c in scored_cards if c["_overlap"] >= 2]
    backfill = [c for c in scored_cards if c["_overlap"] == 1]

    # Sort deterministically: overlap DESC, card_id ASC
    primary.sort(key=lambda c: (-c["_overlap"], c.get("card_id", "")))
    backfill.sort(key=lambda c: (-c["_overlap"], c.get("card_id", "")))

    # Select primary up to max, then backfill
    selected = primary[:max_cards]
    if len(selected) < max_cards:
        remaining_slots = max_cards - len(selected)
        selected.extend(backfill[:remaining_slots])

    # Enforce byte budget
    total_bytes = 0
    final_cards: List[Dict[str, Any]] = []
    max_bytes = config.max_total_bytes or MAX_TOTAL_KNOWLEDGE_BYTES

    for card in selected:
        card_bytes = len(card.get("content", "").encode("utf-8"))
        if total_bytes + card_bytes > max_bytes:
            skipped.append({
                "card_id": card.get("card_id", "unknown"),
                "reason": "byte_budget_exceeded",
            })
            continue
        total_bytes += card_bytes
        # Remove internal scoring field
        clean_card = {k: v for k, v in card.items() if not k.startswith("_")}
        final_cards.append(clean_card)

    # Build manifest
    manifest = {
        "node_id": node_config.get("node_id", ""),
        "skill_name": node_config.get("skill_name", ""),
        "node_domains": sorted(node_domains),
        "cards_matched": len(final_cards),
        "cards_skipped": len(skipped),
        "total_bytes": total_bytes,
        "matches": [
            {
                "card_id": c.get("card_id"),
                "title": c.get("title"),
                "overlap_domains": sorted(
                    _normalize_domains(c.get("domains", [])) & node_domains
                ),
                "trust_level": c.get("trust_level", "unknown"),
            }
            for c in final_cards
        ],
        "skipped": skipped[:10],  # Cap skipped log for readability
    }

    result.cards = final_cards
    result.manifest = manifest

    return result
