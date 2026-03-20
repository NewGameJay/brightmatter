"""
Fireflies ingestion — Configuration and constants.

Filter rules, API settings, and classification thresholds.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern


FIREFLIES_API_URL = "https://api.fireflies.ai/graphql"

RATE_LIMIT_REQUESTS_PER_MINUTE = 55  # Business tier = 60/min, leave headroom

MIN_PARTICIPANT_COUNT = 3

TITLE_EXCLUDE_PATTERNS: list[Pattern[str]] = [
    re.compile(r"\bengineering\b", re.IGNORECASE),
    re.compile(r"\bbuild\s+team\b", re.IGNORECASE),
]

FIREBASE_COLLECTION_TRANSCRIPTS = "meeting_transcripts"
FIREBASE_COLLECTION_INSIGHTS = "meeting_insights"
FIREBASE_COLLECTION_CONNECTIONS = "meeting_connections"

MAX_TRANSCRIPT_CHARS = 500_000
MAX_INSIGHT_CONTENT_CHARS = 4_000

EXTRACTION_MODEL = "claude-haiku"

INSIGHT_TYPES = frozenset({
    "client_request",
    "client_stated_priority",
    "strategic_decision",
    "action_item",
    "methodology",
    "competitive_intel",
    "cross_client_pattern",
})


@dataclass
class FirefliesConfig:
    """Runtime configuration for the ingestion pipeline."""

    api_key: str = ""
    webhook_secret: str = ""
    min_participants: int = MIN_PARTICIPANT_COUNT
    title_exclude_patterns: list[Pattern[str]] = field(
        default_factory=lambda: list(TITLE_EXCLUDE_PATTERNS),
    )
    extraction_model: str = EXTRACTION_MODEL
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "FirefliesConfig":
        return cls(
            api_key=os.environ.get("FIREFLIES_API_KEY", ""),
            webhook_secret=os.environ.get("FIREFLIES_WEBHOOK_SECRET", ""),
        )

    def add_title_exclusion(self, pattern: str) -> None:
        self.title_exclude_patterns.append(re.compile(pattern, re.IGNORECASE))

    def validate(self) -> Optional[str]:
        if not self.api_key:
            return "FIREFLIES_API_KEY not set"
        return None
