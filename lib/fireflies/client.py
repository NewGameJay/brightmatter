"""
Fireflies.ai — GraphQL API Client

Thin wrapper over the Fireflies GraphQL endpoint. Handles auth,
pagination, rate limiting, and retry. No external SDK required.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from lib.fireflies.config import (
    FIREFLIES_API_URL,
    RATE_LIMIT_REQUESTS_PER_MINUTE,
)

logger = logging.getLogger(__name__)


@dataclass
class FirefliesTranscript:
    """Parsed transcript from the Fireflies API."""

    id: str
    title: str
    date: float  # unix timestamp
    duration: int  # seconds
    host_email: str
    organizer_email: str
    participants: List[str]
    meeting_attendees: List[Dict[str, str]]
    speakers: List[Dict[str, str]]
    sentences: List[Dict[str, Any]]
    summary: Dict[str, Any]
    analytics: Dict[str, Any]
    transcript_url: str = ""
    audio_url: str = ""
    meeting_link: str = ""

    @property
    def participant_count(self) -> int:
        return len(self.participants)

    @property
    def attendee_emails(self) -> List[str]:
        return [
            a.get("email", "").lower()
            for a in self.meeting_attendees
            if a.get("email")
        ]

    @property
    def attendee_domains(self) -> set[str]:
        domains = set()
        for email in self.attendee_emails:
            if "@" in email:
                domains.add(email.split("@")[1])
        return domains

    @property
    def full_text(self) -> str:
        """Reconstruct full transcript as markdown."""
        lines = [f"# {self.title}\n"]
        for s in self.sentences:
            speaker = s.get("speaker_name", "Unknown")
            text = s.get("text", "")
            start = s.get("start_time", 0)
            minutes, seconds = divmod(int(start), 60)
            lines.append(f"**{speaker}** *[{minutes:02d}:{seconds:02d}]*: {text}")
        return "\n".join(lines)

    @property
    def action_items(self) -> List[str]:
        return self.summary.get("action_items", []) or []

    @property
    def topics(self) -> List[str]:
        return self.summary.get("topics_discussed", []) or []

    @property
    def keywords(self) -> List[str]:
        return self.summary.get("keywords", []) or []

    @property
    def overview(self) -> str:
        return self.summary.get("overview", "") or ""


class FirefliesClient:
    """GraphQL client for the Fireflies.ai API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        self._last_request_time = 0.0
        self._min_interval = 60.0 / RATE_LIMIT_REQUESTS_PER_MINUTE

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        self._throttle()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(retries + 1):
            try:
                resp = self._session.post(
                    FIREFLIES_API_URL,
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    errors = data["errors"]
                    logger.warning("Fireflies GraphQL errors: %s", errors)
                    if attempt < retries:
                        time.sleep(2 ** attempt)
                        continue
                    raise RuntimeError(f"Fireflies API errors: {errors}")
                return data.get("data", {})
            except requests.exceptions.RequestException as e:
                if attempt < retries:
                    logger.warning(
                        "Fireflies request failed (attempt %d): %s",
                        attempt + 1, e,
                    )
                    time.sleep(2 ** attempt)
                    continue
                raise

        return {}

    def get_transcript(self, transcript_id: str) -> FirefliesTranscript:
        """Fetch a single transcript with full detail."""
        query = """
        query Transcript($id: String!) {
            transcript(id: $id) {
                id
                title
                date
                duration
                host_email
                organizer_email
                participants
                meeting_link
                transcript_url
                audio_url
                meeting_attendees {
                    displayName
                    email
                    phoneNumber
                    location
                }
                speakers {
                    id
                    name
                }
                sentences {
                    speaker_name
                    speaker_id
                    text
                    raw_text
                    start_time
                    end_time
                    ai_filters {
                        task
                        pricing
                        metric
                        question
                        date_and_time
                        sentiment
                    }
                }
                summary {
                    keywords
                    action_items
                    outline
                    shorthand_bullet
                    overview
                    short_summary
                    meeting_type
                    topics_discussed
                }
                analytics {
                    sentiments {
                        positive
                        negative
                        neutral
                    }
                    speakers {
                        name
                        duration
                        word_count
                        questions
                    }
                }
            }
        }
        """
        data = self._query(query, {"id": transcript_id})
        t = data.get("transcript")
        if not t:
            raise ValueError(f"Transcript {transcript_id} not found")
        return self._parse_transcript(t)

    def list_transcripts(
        self,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """List transcripts with basic metadata (for filtering before full fetch)."""
        query = """
        query Transcripts($limit: Int, $skip: Int) {
            transcripts(limit: $limit, skip: $skip) {
                id
                title
                date
                duration
                host_email
                organizer_email
                participants
                meeting_attendees {
                    displayName
                    email
                }
            }
        }
        """
        data = self._query(query, {"limit": limit, "skip": skip})
        return data.get("transcripts", [])

    def get_transcripts_since(
        self,
        since_timestamp: float,
        batch_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch all transcript stubs newer than a given timestamp."""
        all_transcripts: List[Dict[str, Any]] = []
        skip = 0
        while True:
            batch = self.list_transcripts(limit=batch_size, skip=skip)
            if not batch:
                break
            for t in batch:
                ts = t.get("date", 0)
                if isinstance(ts, str):
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except (ValueError, TypeError):
                        ts = 0
                if ts and ts > since_timestamp:
                    all_transcripts.append(t)
                else:
                    return all_transcripts
            skip += batch_size
            if len(batch) < batch_size:
                break
        return all_transcripts

    def _parse_transcript(self, data: Dict[str, Any]) -> FirefliesTranscript:
        date_val = data.get("date", 0)
        if isinstance(date_val, str):
            try:
                from datetime import datetime
                date_val = datetime.fromisoformat(
                    date_val.replace("Z", "+00:00")
                ).timestamp()
            except (ValueError, TypeError):
                date_val = 0

        return FirefliesTranscript(
            id=data.get("id", ""),
            title=data.get("title", ""),
            date=float(date_val or 0),
            duration=int(data.get("duration", 0) or 0),
            host_email=data.get("host_email", "") or "",
            organizer_email=data.get("organizer_email", "") or "",
            participants=data.get("participants", []) or [],
            meeting_attendees=data.get("meeting_attendees", []) or [],
            speakers=data.get("speakers", []) or [],
            sentences=data.get("sentences", []) or [],
            summary=data.get("summary", {}) or {},
            analytics=data.get("analytics", {}) or {},
            transcript_url=data.get("transcript_url", "") or "",
            audio_url=data.get("audio_url", "") or "",
            meeting_link=data.get("meeting_link", "") or "",
        )
