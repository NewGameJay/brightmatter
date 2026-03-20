"""
Expert Knowledge — Ingest Pipeline (Package I3)

Parses raw knowledge sources into bounded, schema-validated knowledge cards.
Supports markdown, text, and JSON formats with card_type heuristics,
dry-run mode, and deterministic card ID generation.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.execution.knowledge import (
    CARD_TYPES,
    MAX_CARD_CONTENT_CHARS,
    MAX_CITATION_EXCERPT_CHARS,
    MAX_CITATIONS_PER_CARD,
    MAX_DOMAINS_PER_CARD,
)


# ── Sanitization ─────────────────────────────────────────────────────

# Closed allowlist of dangerous patterns — ONLY these are removed.
# Adding patterns requires code change, not config.
DANGEROUS_PATTERNS = [
    # Script/iframe/style blocks
    (re.compile(r"<script[\s>].*?</script>", re.IGNORECASE | re.DOTALL), ""),
    (re.compile(r"<iframe[\s>].*?</iframe>", re.IGNORECASE | re.DOTALL), ""),
    (re.compile(r"<style[\s>].*?</style>", re.IGNORECASE | re.DOTALL), ""),
    # javascript: URLs in attributes
    (re.compile(r'(?:href|src|action)\s*=\s*["\']?\s*javascript:', re.IGNORECASE), ""),
    # Event handler attributes
    (re.compile(r'\bon\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE), ""),
    # Prompt injection lines (anchored to line start)
    (re.compile(r"^You are\b.*$", re.MULTILINE | re.IGNORECASE), ""),
    (re.compile(r"^Ignore previous\b.*$", re.MULTILINE | re.IGNORECASE), ""),
    (re.compile(r"^System:\s.*$", re.MULTILINE | re.IGNORECASE), ""),
    (re.compile(r"^Assistant:\s.*$", re.MULTILINE | re.IGNORECASE), ""),
    (re.compile(r"^Human:\s.*$", re.MULTILINE | re.IGNORECASE), ""),
    # Claude tool-call XML (exact tag names only)
    (re.compile(r"</?tool_call>", re.IGNORECASE), ""),
    (re.compile(r"</?tool_result>", re.IGNORECASE), ""),
    (re.compile(r"</?invoke>", re.IGNORECASE), ""),
    (re.compile(r"</?function_calls>", re.IGNORECASE), ""),
]


def sanitize_content(text: str) -> str:
    """
    Preserve-first sanitization pipeline.

    Removes ONLY known dangerous constructs from the closed DANGEROUS_PATTERNS
    list. Preserves markdown tables, HTML tables, code fences, citations,
    Liquid/Jinja templates, and everything else.

    Args:
        text: Raw text content to sanitize.

    Returns:
        Sanitized text, truncated to MAX_CARD_CONTENT_CHARS.
    """
    result = text
    for pattern, replacement in DANGEROUS_PATTERNS:
        result = pattern.sub(replacement, result)

    # Clean up any resulting multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Truncate
    if len(result) > MAX_CARD_CONTENT_CHARS:
        result = result[:MAX_CARD_CONTENT_CHARS]

    return result.strip()


def sanitize_excerpt(text: str) -> str:
    """Sanitize a citation excerpt (max 200 chars)."""
    sanitized = sanitize_content(text)
    if len(sanitized) > MAX_CITATION_EXCERPT_CHARS:
        sanitized = sanitized[:MAX_CITATION_EXCERPT_CHARS]
    return sanitized.strip()


# ── Card ID Generation ────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    """Normalize title for deterministic hashing."""
    return re.sub(r"\s+", " ", title.lower().strip())


def generate_card_id(source_id: str, card_index: int, title: str) -> str:
    """
    Generate deterministic card ID from source_id, index, and title.

    Format: kc-{sha256_hex[:12]}
    Same source structure produces same IDs.
    """
    normalized = _normalize_title(title)
    key = f"{source_id}|{card_index}|{normalized}"
    hash_hex = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"kc-{hash_hex}"


# ── Card Type Heuristics ─────────────────────────────────────────────

def assign_card_type(content: str) -> str:
    """
    Assign card_type based on content heuristics.

    Priority (fallback-first):
    1. Default: definition
    2. checklist: 3+ lines starting with - [ ], - [x], *, or numbered
    3. benchmark_table: has markdown table (|---)
    4. anti_pattern: 2+ occurrences of anti-pattern keywords
    5. example: 2+ occurrences of example keywords
    6. formula: formula-like patterns (= with numbers)
    """
    # Check for checklist (3+ list items)
    list_patterns = [
        r"^\s*[-*]\s*\[[ x]\]",  # - [ ] or - [x]
        r"^\s*[-*]\s+\S",  # - item or * item
        r"^\s*\d+\.\s+\S",  # 1. item
    ]
    list_count = 0
    for line in content.split("\n"):
        for pat in list_patterns:
            if re.match(pat, line):
                list_count += 1
                break
    if list_count >= 3:
        return "checklist"

    # Check for benchmark_table (markdown table)
    if re.search(r"\|[-:]+\|", content):
        return "benchmark_table"

    # Check for anti_pattern (2+ keyword occurrences)
    anti_keywords = ["don't", "avoid", "never", "anti-pattern", "mistake"]
    anti_count = sum(
        1 for kw in anti_keywords
        if kw in content.lower()
    )
    if anti_count >= 2:
        return "anti_pattern"

    # Check for example (2+ keyword occurrences)
    example_keywords = ["example:", "e.g.", "for instance", "case study"]
    example_count = sum(
        1 for kw in example_keywords
        if kw in content.lower()
    )
    if example_count >= 2:
        return "example"

    # Check for formula (= with numbers)
    if re.search(r"\b\w+\s*=\s*[\d.]+\s*[*/+-]", content):
        return "formula"

    return "definition"


# ── Parsers ───────────────────────────────────────────────────────────

def _parse_markdown(raw_text: str) -> List[Dict[str, str]]:
    """
    Parse markdown into sections by headers.

    Split by ## headers first, fall back to # headers,
    then blank-line paragraphs.
    """
    sections = []

    # Try ## headers first
    h2_parts = re.split(r"(?:^|\n)(##\s+.+)", raw_text)
    if len(h2_parts) > 2:  # At least one ## header found
        # h2_parts[0] is preamble, then alternating header/body
        for i in range(1, len(h2_parts), 2):
            header = h2_parts[i].lstrip("#").strip()
            body = h2_parts[i + 1].strip() if i + 1 < len(h2_parts) else ""
            if header and body:
                sections.append({"title": header, "content": body})
        if sections:
            return sections

    # Fall back to # headers
    h1_parts = re.split(r"(?:^|\n)(#\s+.+)", raw_text)
    if len(h1_parts) > 2:
        for i in range(1, len(h1_parts), 2):
            header = h1_parts[i].lstrip("#").strip()
            body = h1_parts[i + 1].strip() if i + 1 < len(h1_parts) else ""
            if header and body:
                sections.append({"title": header, "content": body})
        if sections:
            return sections

    # Fall back to blank-line paragraphs
    paragraphs = re.split(r"\n\n+", raw_text.strip())
    for idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        # Use first line as title
        lines = para.split("\n")
        title = lines[0][:100] if lines else f"Section {idx + 1}"
        sections.append({"title": title, "content": para})

    return sections


def _parse_text(raw_text: str) -> List[Dict[str, str]]:
    """Parse plain text into paragraph-based sections."""
    paragraphs = re.split(r"\n\n+", raw_text.strip())
    sections = []
    current_content = ""
    current_title = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if not current_title:
            lines = para.split("\n")
            current_title = lines[0][:100]
            current_content = para
        elif len(current_content) + len(para) + 2 <= MAX_CARD_CONTENT_CHARS:
            current_content += "\n\n" + para
        else:
            sections.append({"title": current_title, "content": current_content})
            lines = para.split("\n")
            current_title = lines[0][:100]
            current_content = para

    if current_title and current_content:
        sections.append({"title": current_title, "content": current_content})

    return sections


def _parse_json(raw_text: str) -> List[Dict[str, str]]:
    """Parse JSON into card sections."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return [{"title": "JSON Content", "content": raw_text[:MAX_CARD_CONTENT_CHARS]}]

    sections = []
    if isinstance(data, list):
        for idx, item in enumerate(data):
            title = str(item.get("title", item.get("name", f"Item {idx + 1}")))
            if isinstance(item, dict):
                content = json.dumps(item, indent=2)
            else:
                content = str(item)
            sections.append({"title": title[:100], "content": content[:MAX_CARD_CONTENT_CHARS]})
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                content = json.dumps(value, indent=2)
            elif isinstance(value, list):
                content = json.dumps(value, indent=2)
            else:
                content = str(value)
            sections.append({"title": str(key)[:100], "content": content[:MAX_CARD_CONTENT_CHARS]})
    else:
        sections.append({"title": "JSON Content", "content": str(data)[:MAX_CARD_CONTENT_CHARS]})

    return sections


# ── Ingest Result ─────────────────────────────────────────────────────

@dataclass
class IngestResult:
    """Result of ingesting a source into cards."""

    cards_created: int = 0
    cards_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    card_ids: List[str] = field(default_factory=list)


# ── Main Ingest Function ─────────────────────────────────────────────

def ingest_source_to_cards(
    source_path: Path,
    source_meta: Dict[str, Any],
    store: Any,  # KnowledgeStore instance
    dry_run: bool = False,
) -> IngestResult:
    """
    Ingest a source file into knowledge cards.

    Reads the raw source, parses into sections, assigns card types,
    sanitizes content, generates deterministic IDs, validates against
    schema, and writes to the store.

    Args:
        source_path: Path to the raw source file.
        source_meta: Source metadata dict.
        store: KnowledgeStore instance.
        dry_run: If True, don't write cards, just return what would be created.

    Returns:
        IngestResult with counts and any errors.
    """
    result = IngestResult()

    if not source_path.exists():
        result.errors.append(f"Source file not found: {source_path}")
        return result

    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result.errors.append(f"Failed to read source file: {e}")
        return result

    if not raw_text.strip():
        result.errors.append("Source file is empty")
        return result

    source_id = source_meta["source_id"]
    source_format = source_meta.get("format", "markdown")
    source_domains = source_meta.get("domains", [])
    trust_level = source_meta.get("trust_level", "unreviewed")
    version_hash = source_meta.get("version_hash", "")

    # Parse into sections based on format
    if source_format == "json":
        sections = _parse_json(raw_text)
    elif source_format == "text":
        sections = _parse_text(raw_text)
    else:  # markdown (default)
        sections = _parse_markdown(raw_text)

    if not sections:
        result.warnings.append("No sections extracted from source")
        return result

    now = datetime.now(timezone.utc).isoformat()

    for idx, section in enumerate(sections):
        title = section.get("title", f"Card {idx + 1}")
        raw_content = section.get("content", "")

        if not raw_content.strip():
            result.cards_skipped += 1
            continue

        # Sanitize content
        content = sanitize_content(raw_content)
        if not content:
            result.cards_skipped += 1
            result.warnings.append(f"Section '{title}' empty after sanitization")
            continue

        # Assign card type
        card_type = assign_card_type(content)

        # Generate deterministic card ID
        card_id = generate_card_id(source_id, idx, title)

        # Build citations
        citations = []
        source_location = f"section: {title}"
        excerpt = sanitize_excerpt(raw_content[:MAX_CITATION_EXCERPT_CHARS])
        if excerpt:
            citations.append({
                "source_location": source_location[:200],
                "excerpt": excerpt,
            })
        citations = citations[:MAX_CITATIONS_PER_CARD]

        # Build card dict
        card = {
            "card_id": card_id,
            "source_id": source_id,
            "card_type": card_type,
            "title": title[:200],
            "domains": source_domains[:MAX_DOMAINS_PER_CARD],
            "content": content,
            "citations": citations,
            "trust_level": trust_level,
            "source_version_hash": version_hash,
            "created_at": now,
            "version": "1",
        }

        if dry_run:
            result.card_ids.append(card_id)
            result.cards_created += 1
        else:
            try:
                store.write_card(card)
                result.card_ids.append(card_id)
                result.cards_created += 1
            except Exception as e:
                result.errors.append(f"Failed to write card '{title}': {e}")

    return result


def reingest_source(
    source_id: str,
    store: Any,  # KnowledgeStore instance
    force: bool = False,
    dry_run: bool = False,
) -> IngestResult:
    """
    Re-ingest a source, with change detection.

    If the source file has changed (or --force), purges old cards
    and re-ingests from current content.

    Args:
        source_id: ID of the source to re-ingest.
        store: KnowledgeStore instance.
        force: Skip change detection, always re-ingest.
        dry_run: Don't write, just preview.

    Returns:
        IngestResult with counts and any errors/warnings.
    """
    source = store.get_source(source_id)
    if not source:
        result = IngestResult()
        result.errors.append(f"Source not found: {source_id}")
        return result

    # Check for changes
    if not force and not store.detect_source_changes(source_id):
        result = IngestResult()
        result.warnings.append(
            f"Source '{source_id}' unchanged. Use --force to re-ingest."
        )
        return result

    # Get raw file path
    raw_path = store.get_raw_path(source_id)
    if not raw_path:
        result = IngestResult()
        result.errors.append(f"Raw file not found for source: {source_id}")
        return result

    # Purge existing cards (unless dry-run)
    if not dry_run:
        purged = store.purge_cards_for_source(source_id)

    # Re-ingest
    return ingest_source_to_cards(raw_path, source, store, dry_run=dry_run)
