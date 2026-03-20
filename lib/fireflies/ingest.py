"""
Fireflies ingestion — Orchestrator

Central pipeline: fetch → filter → classify → extract → store → connect.

Entry points:
    ingest_meeting()  — Process a single meeting by Fireflies ID (webhook trigger)
    sync_new()        — Fetch and process all new meetings since last sync (CLI/cron)
    backfill()        — Re-process historical meetings within a date range
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lib.fireflies.classifier import Classification, classify_meeting, _load_client_domain_map
from lib.fireflies.client import FirefliesClient, FirefliesTranscript
from lib.fireflies.config import FirefliesConfig
from lib.fireflies.extractor import (
    CrossCallConnection,
    MeetingInsight,
    detect_connections,
    extract_insights,
)
from lib.fireflies.store import (
    bridge_to_knowledge_store,
    get_existing_insights,
    get_last_sync_timestamp,
    is_transcript_ingested,
    set_last_sync_timestamp,
    store_connections,
    store_insights,
    store_transcript,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of processing a single meeting."""

    meeting_id: str
    title: str
    status: str  # "ingested", "skipped", "filtered", "error"
    classification: Optional[Classification] = None
    insights_count: int = 0
    connections_count: int = 0
    knowledge_cards_count: int = 0
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "title": self.title,
            "status": self.status,
            "meeting_type": self.classification.meeting_type if self.classification else None,
            "client_id": self.classification.client_id if self.classification else None,
            "insights_count": self.insights_count,
            "connections_count": self.connections_count,
            "knowledge_cards_count": self.knowledge_cards_count,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SyncResult:
    """Result of a full sync operation."""

    meetings_found: int = 0
    meetings_ingested: int = 0
    meetings_skipped: int = 0
    meetings_filtered: int = 0
    meetings_errored: int = 0
    total_insights: int = 0
    total_connections: int = 0
    total_knowledge_cards: int = 0
    results: List[IngestionResult] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meetings_found": self.meetings_found,
            "meetings_ingested": self.meetings_ingested,
            "meetings_skipped": self.meetings_skipped,
            "meetings_filtered": self.meetings_filtered,
            "meetings_errored": self.meetings_errored,
            "total_insights": self.total_insights,
            "total_connections": self.total_connections,
            "total_knowledge_cards": self.total_knowledge_cards,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
        }


def ingest_meeting(
    meeting_id: str,
    config: Optional[FirefliesConfig] = None,
    force: bool = False,
) -> IngestionResult:
    """
    Process a single meeting by Fireflies ID.

    This is the primary entry point for webhook-triggered ingestion.
    Fetches the full transcript, classifies it, extracts insights,
    detects cross-call connections, and stores everything.

    Args:
        meeting_id: Fireflies meeting/transcript ID
        config: Pipeline configuration (defaults to env-based)
        force: Re-process even if already ingested
    """
    start = time.time()
    config = config or FirefliesConfig.from_env()

    err = config.validate()
    if err:
        return IngestionResult(
            meeting_id=meeting_id, title="", status="error", error=err,
        )

    if not force and is_transcript_ingested(meeting_id):
        return IngestionResult(
            meeting_id=meeting_id, title="", status="skipped",
            error="Already ingested (use force=True to re-process)",
        )

    client = FirefliesClient(config.api_key)

    # 1. Fetch full transcript
    try:
        transcript = client.get_transcript(meeting_id)
    except Exception as e:
        return IngestionResult(
            meeting_id=meeting_id, title="", status="error",
            error=f"Failed to fetch transcript: {e}",
        )

    return _process_transcript(transcript, config, start)


def sync_new(
    config: Optional[FirefliesConfig] = None,
) -> SyncResult:
    """
    Fetch and process all new meetings since the last sync.

    Reads the last sync timestamp from Firebase, fetches all newer
    transcripts from Fireflies, processes each one, and updates
    the sync timestamp.
    """
    start = time.time()
    config = config or FirefliesConfig.from_env()
    result = SyncResult()

    err = config.validate()
    if err:
        logger.error("Config validation failed: %s", err)
        return result

    client = FirefliesClient(config.api_key)
    last_sync = get_last_sync_timestamp()

    logger.info(
        "Syncing meetings since %s",
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(last_sync)) if last_sync else "beginning",
    )

    try:
        stubs = client.get_transcripts_since(last_sync)
    except Exception as e:
        logger.error("Failed to list transcripts: %s", e)
        return result

    result.meetings_found = len(stubs)
    logger.info("Found %d new meetings", len(stubs))

    for stub in stubs:
        mid = stub.get("id", "")
        if not mid:
            continue

        if is_transcript_ingested(mid):
            result.meetings_skipped += 1
            result.results.append(IngestionResult(
                meeting_id=mid,
                title=stub.get("title", ""),
                status="skipped",
            ))
            continue

        # Quick pre-filter on participant count from stub data
        participants = stub.get("participants", [])
        if len(participants) < config.min_participants:
            result.meetings_filtered += 1
            result.results.append(IngestionResult(
                meeting_id=mid,
                title=stub.get("title", ""),
                status="filtered",
                error=f"Only {len(participants)} participants",
            ))
            continue

        # Fetch full transcript and process
        try:
            transcript = client.get_transcript(mid)
            ing_result = _process_transcript(transcript, config, time.time())
        except Exception as e:
            logger.error("Failed to process meeting %s: %s", mid, e)
            ing_result = IngestionResult(
                meeting_id=mid,
                title=stub.get("title", ""),
                status="error",
                error=str(e),
            )

        result.results.append(ing_result)

        if ing_result.status == "ingested":
            result.meetings_ingested += 1
            result.total_insights += ing_result.insights_count
            result.total_connections += ing_result.connections_count
            result.total_knowledge_cards += ing_result.knowledge_cards_count
        elif ing_result.status == "filtered":
            result.meetings_filtered += 1
        elif ing_result.status == "error":
            result.meetings_errored += 1

    set_last_sync_timestamp(time.time())
    result.duration_ms = int((time.time() - start) * 1000)

    logger.info(
        "Sync complete: %d found, %d ingested, %d filtered, %d skipped, %d errors. "
        "%d insights, %d connections, %d knowledge cards. Took %dms.",
        result.meetings_found, result.meetings_ingested, result.meetings_filtered,
        result.meetings_skipped, result.meetings_errored,
        result.total_insights, result.total_connections, result.total_knowledge_cards,
        result.duration_ms,
    )
    return result


def backfill(
    since_days: int = 90,
    config: Optional[FirefliesConfig] = None,
    force: bool = False,
) -> SyncResult:
    """
    Re-process historical meetings within a date range.

    Fetches all meetings from the past N days and processes them,
    optionally overwriting existing data.
    """
    config = config or FirefliesConfig.from_env()

    err = config.validate()
    if err:
        logger.error("Config validation failed: %s", err)
        return SyncResult()

    since_ts = time.time() - (since_days * 86400)
    client = FirefliesClient(config.api_key)

    try:
        stubs = client.get_transcripts_since(since_ts)
    except Exception as e:
        logger.error("Failed to list transcripts for backfill: %s", e)
        return SyncResult()

    result = SyncResult(meetings_found=len(stubs))
    start = time.time()

    for stub in stubs:
        mid = stub.get("id", "")
        if not mid:
            continue

        if not force and is_transcript_ingested(mid):
            result.meetings_skipped += 1
            continue

        try:
            transcript = client.get_transcript(mid)
            ing_result = _process_transcript(transcript, config, time.time())
        except Exception as e:
            logger.error("Backfill: failed to process %s: %s", mid, e)
            ing_result = IngestionResult(
                meeting_id=mid, title=stub.get("title", ""),
                status="error", error=str(e),
            )

        result.results.append(ing_result)
        if ing_result.status == "ingested":
            result.meetings_ingested += 1
            result.total_insights += ing_result.insights_count
            result.total_connections += ing_result.connections_count

    result.duration_ms = int((time.time() - start) * 1000)
    return result


# ── Internal pipeline ──────────────────────────────────────────────────


def _process_transcript(
    transcript: FirefliesTranscript,
    config: FirefliesConfig,
    start_time: float,
) -> IngestionResult:
    """Full processing pipeline for a single transcript."""

    # 1. Classify
    client_domain_map = _load_client_domain_map()
    classification = classify_meeting(transcript, config, client_domain_map)

    if classification.excluded:
        return IngestionResult(
            meeting_id=transcript.id,
            title=transcript.title,
            status="filtered",
            classification=classification,
            error=classification.exclusion_reason,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    # 2. Store full transcript (always, before extraction)
    stored_id = store_transcript(transcript, classification)
    if stored_id is None and not config.dry_run:
        return IngestionResult(
            meeting_id=transcript.id,
            title=transcript.title,
            status="error",
            classification=classification,
            error="Failed to store transcript in Firebase",
            duration_ms=int((time.time() - start_time) * 1000),
        )

    if config.dry_run:
        return IngestionResult(
            meeting_id=transcript.id,
            title=transcript.title,
            status="ingested",
            classification=classification,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    # 3. Extract insights
    insights = extract_insights(transcript, classification)

    # 4. Store insights
    if insights:
        store_insights(insights, transcript.id)

    # 5. Detect cross-call connections
    all_domains = set()
    for ins in insights:
        all_domains.update(ins.domains)

    existing = get_existing_insights(
        domains=list(all_domains)[:5] if all_domains else None
    )
    connections = detect_connections(insights, existing)

    # 6. Store connections
    if connections:
        store_connections(connections, transcript.id)

    # 7. Bridge high-value items to knowledge store
    cards_count = bridge_to_knowledge_store(
        insights, connections, transcript
    )

    elapsed = int((time.time() - start_time) * 1000)

    return IngestionResult(
        meeting_id=transcript.id,
        title=transcript.title,
        status="ingested",
        classification=classification,
        insights_count=len(insights),
        connections_count=len(connections),
        knowledge_cards_count=cards_count,
        duration_ms=elapsed,
    )
