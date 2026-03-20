"""
Fireflies ingestion — Meeting Classifier

Routes each transcript to the right processing path:
  - client:   External attendee matches a known client → tag with client_id
  - internal: All attendees are internal team members
  - sales:    External attendee, no client match (prospect/sales call)
  - other:    Unclassifiable

Also enforces participant count and title exclusion filters.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lib.fireflies.client import FirefliesTranscript
from lib.fireflies.config import FirefliesConfig

logger = logging.getLogger(__name__)


@dataclass
class Classification:
    """Result of classifying a meeting transcript."""

    meeting_type: str  # "client" | "internal" | "sales" | "other"
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    excluded: bool = False
    exclusion_reason: str = ""


# Known internal domains — expand as needed
_INTERNAL_DOMAINS: Set[str] = {
    "marketerhire.com",
    "mh1.ai",
    "mh-1.com",
}


def _load_client_domain_map(clients_dir: str = "clients") -> Dict[str, Dict[str, str]]:
    """
    Build a mapping from email domain → client info by scanning
    client config/datasources.json and context files.

    Returns: {domain: {"client_id": ..., "client_name": ...}}
    """
    domain_map: Dict[str, Dict[str, str]] = {}
    clients_path = Path(clients_dir)

    if not clients_path.exists():
        return domain_map

    for client_dir in clients_path.iterdir():
        if not client_dir.is_dir() or client_dir.name.startswith("."):
            continue

        client_slug = client_dir.name
        client_name = client_slug.replace("-", " ").title()

        # Try datasources.json for website domain
        ds_path = client_dir / "config" / "datasources.json"
        if ds_path.exists():
            try:
                ds = json.loads(ds_path.read_text())
                website = ds.get("client", {}).get("website", "")
                if website:
                    domain = _extract_domain_from_url(website)
                    if domain:
                        domain_map[domain] = {
                            "client_id": client_slug,
                            "client_name": ds.get("client", {}).get("name", client_name),
                        }
                company = ds.get("client", {}).get("name", "")
                if company:
                    client_name = company
            except (json.JSONDecodeError, OSError):
                pass

        # Try .client_id file for Firebase ID
        cid_path = client_dir / ".client_id"
        if cid_path.exists():
            try:
                firebase_id = cid_path.read_text().strip()
                for domain, info in list(domain_map.items()):
                    if info["client_id"] == client_slug:
                        info["firebase_id"] = firebase_id
            except OSError:
                pass

    return domain_map


def _extract_domain_from_url(url: str) -> Optional[str]:
    url = url.strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    url = url.split("/")[0]
    return url if "." in url else None


def classify_meeting(
    transcript: FirefliesTranscript,
    config: FirefliesConfig,
    client_domain_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Classification:
    """
    Classify a meeting transcript by type and client attribution.

    Filters:
      1. Participant count must be >= config.min_participants
      2. Title must not match any exclusion pattern

    Classification logic:
      1. If all attendee domains are internal → "internal"
      2. If any external domain matches a known client → "client"
      3. If external attendees but no client match → "sales"
      4. Otherwise → "other"
    """
    # --- Filter: participant count ---
    if transcript.participant_count < config.min_participants:
        return Classification(
            meeting_type="other",
            excluded=True,
            exclusion_reason=(
                f"Only {transcript.participant_count} participants "
                f"(minimum: {config.min_participants})"
            ),
        )

    # --- Filter: title exclusion ---
    for pattern in config.title_exclude_patterns:
        if pattern.search(transcript.title):
            return Classification(
                meeting_type="other",
                excluded=True,
                exclusion_reason=f"Title matches exclusion pattern: {pattern.pattern}",
            )

    # --- Classification ---
    if client_domain_map is None:
        client_domain_map = _load_client_domain_map()

    attendee_domains = transcript.attendee_domains
    external_domains = attendee_domains - _INTERNAL_DOMAINS

    if not attendee_domains:
        # No email data — classify by title/content heuristics
        return _classify_by_title(transcript, client_domain_map)

    if not external_domains:
        return Classification(
            meeting_type="internal",
            confidence=0.9,
            reason="All attendees are from internal domains",
        )

    # Check for client match
    for domain in external_domains:
        if domain in client_domain_map:
            info = client_domain_map[domain]
            return Classification(
                meeting_type="client",
                client_id=info["client_id"],
                client_name=info.get("client_name"),
                confidence=0.95,
                reason=f"Attendee domain {domain} matches client {info['client_id']}",
            )

    return Classification(
        meeting_type="sales",
        confidence=0.7,
        reason=f"External domains {external_domains} don't match any known client",
    )


def _classify_by_title(
    transcript: FirefliesTranscript,
    client_domain_map: Dict[str, Dict[str, str]],
) -> Classification:
    """Fallback classification when attendee emails aren't available."""
    title_lower = transcript.title.lower()

    for _domain, info in client_domain_map.items():
        client_name = info.get("client_name", "").lower()
        if client_name and client_name in title_lower:
            return Classification(
                meeting_type="client",
                client_id=info["client_id"],
                client_name=info.get("client_name"),
                confidence=0.7,
                reason=f"Title contains client name '{info.get('client_name')}'",
            )

    internal_keywords = ["standup", "retro", "sprint", "1:1", "sync", "ops review"]
    if any(kw in title_lower for kw in internal_keywords):
        return Classification(
            meeting_type="internal",
            confidence=0.6,
            reason="Title matches internal meeting pattern",
        )

    return Classification(
        meeting_type="other",
        confidence=0.3,
        reason="Could not determine meeting type from available data",
    )
