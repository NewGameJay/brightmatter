"""
Fireflies ingestion — Firebase Storage Layer

Stores full transcripts, extracted insights, and cross-call connections
in Firebase Firestore. All data is queryable by meeting ID, client ID,
concept tags, and date range.

Also bridges high-value insights into the knowledge_store/ as cards
for injection into skill execution contexts.

Collections:
    meeting_transcripts/{meeting_id}  — Full transcript + metadata
    meeting_insights/{insight_id}     — Individual extracted insights
    meeting_connections/{conn_id}     — Cross-call pattern connections
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.fireflies.client import FirefliesTranscript
from lib.fireflies.classifier import Classification
from lib.fireflies.config import (
    FIREBASE_COLLECTION_CONNECTIONS,
    FIREBASE_COLLECTION_INSIGHTS,
    FIREBASE_COLLECTION_TRANSCRIPTS,
    MAX_TRANSCRIPT_CHARS,
)
from lib.fireflies.extractor import CrossCallConnection, MeetingInsight

logger = logging.getLogger(__name__)


def _get_firestore():
    """Get Firestore client via the shared singleton."""
    try:
        from lib.firebase_client import get_firebase_client
        fb = get_firebase_client()
        return fb.db
    except Exception as e:
        logger.error("Firestore unavailable: %s", e)
        return None


# ── Transcript Storage ─────────────────────────────────────────────────


def store_transcript(
    transcript: FirefliesTranscript,
    classification: Classification,
) -> Optional[str]:
    """
    Store a full transcript in Firebase, queryable by Fireflies meeting ID.

    Stores the complete markdown transcript, all metadata from Fireflies
    (attendees, speakers, analytics, summary), and our classification.

    Returns the Fireflies meeting ID used as the document key, or None on failure.
    """
    db = _get_firestore()
    if db is None:
        return None

    full_text = transcript.full_text
    if len(full_text) > MAX_TRANSCRIPT_CHARS:
        full_text = full_text[:MAX_TRANSCRIPT_CHARS]
        logger.warning(
            "Transcript %s truncated from %d to %d chars",
            transcript.id, len(transcript.full_text), MAX_TRANSCRIPT_CHARS,
        )

    doc = {
        "fireflies_id": transcript.id,
        "title": transcript.title,
        "date": transcript.date,
        "date_iso": datetime.fromtimestamp(
            transcript.date, tz=timezone.utc
        ).isoformat() if transcript.date else None,
        "duration": transcript.duration,
        "host_email": transcript.host_email,
        "organizer_email": transcript.organizer_email,
        "participants": transcript.participants,
        "participant_count": transcript.participant_count,
        "meeting_attendees": transcript.meeting_attendees,
        "speakers": transcript.speakers,
        "transcript_url": transcript.transcript_url,
        "audio_url": transcript.audio_url,

        "classification": {
            "meeting_type": classification.meeting_type,
            "client_id": classification.client_id,
            "client_name": classification.client_name,
            "confidence": classification.confidence,
            "reason": classification.reason,
        },

        "full_transcript": full_text,

        "summary": {
            "overview": transcript.overview,
            "action_items": transcript.action_items,
            "topics": transcript.topics,
            "keywords": transcript.keywords,
        },

        "analytics": transcript.analytics,

        "ingested_at": time.time(),
        "insight_ids": [],
        "connection_ids": [],
    }

    try:
        doc_ref = db.collection(FIREBASE_COLLECTION_TRANSCRIPTS).document(transcript.id)
        doc_ref.set(doc)
        logger.info("Stored transcript %s: %s", transcript.id, transcript.title)
        return transcript.id
    except Exception as e:
        logger.error("Failed to store transcript %s: %s", transcript.id, e)
        return None


def get_transcript(meeting_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a full transcript from Firebase by Fireflies meeting ID."""
    db = _get_firestore()
    if db is None:
        return None
    try:
        doc = db.collection(FIREBASE_COLLECTION_TRANSCRIPTS).document(meeting_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error("Failed to get transcript %s: %s", meeting_id, e)
        return None


def is_transcript_ingested(meeting_id: str) -> bool:
    """Check if a transcript has already been ingested."""
    db = _get_firestore()
    if db is None:
        return False
    try:
        doc = db.collection(FIREBASE_COLLECTION_TRANSCRIPTS).document(meeting_id).get()
        return doc.exists
    except Exception:
        return False


def list_transcripts(
    client_id: Optional[str] = None,
    meeting_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List transcripts with optional filtering by client or type."""
    db = _get_firestore()
    if db is None:
        return []
    try:
        query = db.collection(FIREBASE_COLLECTION_TRANSCRIPTS)
        if client_id:
            query = query.where("classification.client_id", "==", client_id)
        if meeting_type:
            query = query.where("classification.meeting_type", "==", meeting_type)
        query = query.order_by("date", direction="DESCENDING").limit(limit)
        return [doc.to_dict() for doc in query.stream()]
    except Exception as e:
        logger.error("Failed to list transcripts: %s", e)
        return []


# ── Insight Storage ────────────────────────────────────────────────────


def store_insights(
    insights: List[MeetingInsight],
    meeting_id: str,
) -> List[str]:
    """
    Store extracted insights in Firebase and link them to their transcript.

    Returns list of stored insight IDs.
    """
    db = _get_firestore()
    if db is None:
        return []

    stored_ids: List[str] = []

    for insight in insights:
        try:
            doc_ref = db.collection(FIREBASE_COLLECTION_INSIGHTS).document(
                insight.insight_id
            )
            doc_ref.set(insight.to_dict())
            stored_ids.append(insight.insight_id)
        except Exception as e:
            logger.error(
                "Failed to store insight %s: %s", insight.insight_id, e
            )

    # Link insight IDs to the transcript document
    if stored_ids:
        try:
            from google.cloud.firestore_v1 import ArrayUnion
        except ImportError:
            from google.cloud.firestore import ArrayUnion  # type: ignore
        try:
            db.collection(FIREBASE_COLLECTION_TRANSCRIPTS).document(
                meeting_id
            ).update({"insight_ids": ArrayUnion(stored_ids)})
        except Exception as e:
            logger.warning("Failed to link insights to transcript %s: %s", meeting_id, e)

    logger.info("Stored %d insights for meeting %s", len(stored_ids), meeting_id)
    return stored_ids


def get_existing_insights(
    domains: Optional[List[str]] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Retrieve existing insights for cross-call pattern detection.

    When domains are specified, filters to insights sharing at least one domain.
    Otherwise returns the most recent insights.
    """
    db = _get_firestore()
    if db is None:
        return []

    try:
        if domains:
            all_results: List[Dict[str, Any]] = []
            for domain in domains[:5]:
                query = (
                    db.collection(FIREBASE_COLLECTION_INSIGHTS)
                    .where("domains", "array_contains", domain)
                    .limit(limit)
                )
                for doc in query.stream():
                    data = doc.to_dict()
                    if data and data.get("insight_id") not in {
                        r.get("insight_id") for r in all_results
                    }:
                        all_results.append(data)
            return all_results[:limit]
        else:
            query = (
                db.collection(FIREBASE_COLLECTION_INSIGHTS)
                .order_by("created_at", direction="DESCENDING")
                .limit(limit)
            )
            return [doc.to_dict() for doc in query.stream()]
    except Exception as e:
        logger.error("Failed to get existing insights: %s", e)
        return []


def get_client_priorities(
    client_id: str,
    include_mirrored: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieve all client-stated priorities and mirror-flagged insights
    for a specific client. Used by strategy/assessment deck generation
    to reflect the client's own words back to them.

    Returns insights sorted by confidence (highest first).
    """
    db = _get_firestore()
    if db is None:
        return []

    results: List[Dict[str, Any]] = []
    try:
        # Always fetch client_stated_priority
        q = (
            db.collection(FIREBASE_COLLECTION_INSIGHTS)
            .where("client_id", "==", client_id)
            .where("insight_type", "==", "client_stated_priority")
        )
        for doc in q.stream():
            data = doc.to_dict()
            if data:
                results.append(data)

        # Also fetch anything flagged for deliverable mirroring
        if include_mirrored:
            q2 = (
                db.collection(FIREBASE_COLLECTION_INSIGHTS)
                .where("client_id", "==", client_id)
                .where("mirror_in_deliverables", "==", True)
            )
            seen_ids = {r.get("insight_id") for r in results}
            for doc in q2.stream():
                data = doc.to_dict()
                if data and data.get("insight_id") not in seen_ids:
                    results.append(data)

    except Exception as e:
        logger.error("Failed to get client priorities for %s: %s", client_id, e)

    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return results


# ── Connection Storage ─────────────────────────────────────────────────


def store_connections(
    connections: List[CrossCallConnection],
    meeting_id: str,
) -> List[str]:
    """Store cross-call connections and link them to the transcript."""
    db = _get_firestore()
    if db is None:
        return []

    stored_ids: List[str] = []

    for conn in connections:
        try:
            doc_ref = db.collection(FIREBASE_COLLECTION_CONNECTIONS).document(
                conn.connection_id
            )
            doc_ref.set(conn.to_dict())
            stored_ids.append(conn.connection_id)
        except Exception as e:
            logger.error(
                "Failed to store connection %s: %s", conn.connection_id, e
            )

    if stored_ids:
        try:
            from google.cloud.firestore_v1 import ArrayUnion
        except ImportError:
            from google.cloud.firestore import ArrayUnion  # type: ignore
        try:
            db.collection(FIREBASE_COLLECTION_TRANSCRIPTS).document(
                meeting_id
            ).update({"connection_ids": ArrayUnion(stored_ids)})
        except Exception as e:
            logger.warning(
                "Failed to link connections to transcript %s: %s", meeting_id, e
            )

    return stored_ids


def get_connections_for_meeting(meeting_id: str) -> List[Dict[str, Any]]:
    """Get all cross-call connections involving a specific meeting."""
    db = _get_firestore()
    if db is None:
        return []
    try:
        query = (
            db.collection(FIREBASE_COLLECTION_CONNECTIONS)
            .where("meeting_ids", "array_contains", meeting_id)
        )
        return [doc.to_dict() for doc in query.stream()]
    except Exception as e:
        logger.error("Failed to get connections for %s: %s", meeting_id, e)
        return []


def get_connections_by_concept(concept: str) -> List[Dict[str, Any]]:
    """Find all connections involving a specific concept tag."""
    db = _get_firestore()
    if db is None:
        return []
    try:
        query = (
            db.collection(FIREBASE_COLLECTION_CONNECTIONS)
            .where("shared_concepts", "array_contains", concept)
        )
        return [doc.to_dict() for doc in query.stream()]
    except Exception as e:
        logger.error("Failed to get connections for concept %s: %s", concept, e)
        return []


# ── Knowledge Card Bridge ──────────────────────────────────────────────


def bridge_to_knowledge_store(
    insights: List[MeetingInsight],
    connections: List[CrossCallConnection],
    transcript: FirefliesTranscript,
    store_dir: str = "knowledge_store",
) -> int:
    """
    Write high-value insights and connections to the knowledge_store/
    as cards that can be injected into sandbox execution contexts.

    Bridge criteria (any of):
      - client_stated_priority: ALWAYS bridged, regardless of confidence.
        These carry the client's verbatim words and must surface in every
        deliverable touching that client.
      - mirror_in_deliverables=true: ALWAYS bridged. The client values this.
      - methodology / cross_client_pattern / competitive_intel with
        confidence >= 0.7

    Returns number of cards written.
    """
    try:
        from lib.execution.knowledge.store import KnowledgeStore
    except ImportError:
        logger.warning("Knowledge store not available — skipping card bridge")
        return 0

    store = KnowledgeStore(store_dir)
    cards_written = 0
    now = datetime.now(timezone.utc).isoformat()

    confidence_gated_types = {"methodology", "cross_client_pattern", "competitive_intel"}

    for insight in insights:
        # Determine if this insight should be bridged
        is_client_priority = insight.insight_type == "client_stated_priority"
        must_mirror = insight.mirror_in_deliverables
        passes_confidence_gate = (
            insight.insight_type in confidence_gated_types
            and insight.confidence >= 0.7
        )

        if not (is_client_priority or must_mirror or passes_confidence_gate):
            continue

        # Map to knowledge card type
        if is_client_priority:
            card_type = "definition"
        elif insight.insight_type == "methodology":
            card_type = "checklist"
        elif insight.insight_type == "competitive_intel":
            card_type = "example"
        else:
            card_type = "definition"

        meeting_date = (
            datetime.fromtimestamp(transcript.date, tz=timezone.utc).strftime('%Y-%m-%d')
            if transcript.date else "unknown date"
        )

        # Build content — client priorities include the verbatim quote prominently
        content_parts = [insight.content]
        if insight.client_verbatim:
            content_parts.insert(
                0, f'Client verbatim: "{insight.client_verbatim}"\n'
            )
        if must_mirror:
            content_parts.append(
                "\n[MIRROR IN DELIVERABLES] This must be reflected "
                "in strategy decks, assessments, and presentations for this client."
            )
        content_parts.append(
            f"\nSource: Meeting '{transcript.title}' ({meeting_date})\n"
            f"Speaker: {insight.speaker}\n"
            f"Meeting ID: {transcript.id}"
        )

        card = {
            "card_id": f"kc-ff-{insight.insight_id[3:]}",
            "source_id": f"fireflies-{transcript.id}",
            "card_type": card_type,
            "title": insight.title,
            "domains": insight.domains,
            "content": "\n".join(content_parts),
            "citations": [{
                "source": f"Fireflies meeting: {transcript.title}",
                "meeting_id": transcript.id,
                "speaker": insight.speaker,
                "date": datetime.fromtimestamp(
                    transcript.date, tz=timezone.utc
                ).isoformat() if transcript.date else "",
            }],
            "trust_level": "reviewed" if is_client_priority else "unreviewed",
            "created_at": now,
            "version": "1",
            "mirror_in_deliverables": must_mirror or is_client_priority,
            "client_id": insight.client_id,
        }

        try:
            store.write_card(card)
            cards_written += 1
        except Exception as e:
            logger.warning("Failed to write knowledge card for %s: %s", insight.insight_id, e)

    # Bridge strong cross-call connections as cards too
    for conn in connections:
        if conn.strength < 0.5:
            continue

        card = {
            "card_id": f"kc-ff-{conn.connection_id[3:]}",
            "source_id": "fireflies-connections",
            "card_type": "example",
            "title": f"Cross-call pattern: {conn.title}",
            "domains": conn.domains,
            "content": (
                f"{conn.description}\n\n"
                f"Pattern type: {conn.pattern_type}\n"
                f"Shared concepts: {', '.join(conn.shared_concepts)}\n"
                f"Strength: {conn.strength}\n"
                f"Meetings involved: {', '.join(conn.meeting_ids)}"
            ),
            "citations": [
                {"meeting_id": mid, "source": f"Fireflies meeting {mid}"}
                for mid in conn.meeting_ids
            ],
            "trust_level": "unreviewed",
            "created_at": now,
            "version": "1",
        }

        try:
            store.write_card(card)
            cards_written += 1
        except Exception as e:
            logger.warning(
                "Failed to write connection card %s: %s", conn.connection_id, e
            )

    if cards_written:
        logger.info("Bridged %d items to knowledge store", cards_written)

    return cards_written


# ── Sync state tracking ───────────────────────────────────────────────


def get_last_sync_timestamp() -> float:
    """Get the timestamp of the last successful sync from Firebase."""
    db = _get_firestore()
    if db is None:
        return 0.0
    try:
        doc = db.collection("system").document("fireflies_sync").get()
        if doc.exists:
            return float(doc.to_dict().get("last_sync_at", 0))
    except Exception:
        pass
    return 0.0


def set_last_sync_timestamp(ts: float) -> None:
    """Update the last sync timestamp in Firebase."""
    db = _get_firestore()
    if db is None:
        return
    try:
        db.collection("system").document("fireflies_sync").set({
            "last_sync_at": ts,
            "updated_at": time.time(),
        }, merge=True)
    except Exception as e:
        logger.warning("Failed to update sync timestamp: %s", e)
