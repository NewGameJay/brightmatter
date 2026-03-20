"""
MH1 Pending Outcome Store

Firebase-backed persistent store for predictions awaiting real-world
outcome measurement. Predictions are registered at execution time and
resolved via deferred checkpoints at 24h (adoption) and 7d (performance).

Firebase path: system/intelligence/pending_outcomes/{client_id}/{prediction_id}

Lifecycle:
    pending -> checkpoint_24h -> checkpoint_7d -> closed
                                               -> expired (if no platform data after 14d)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OutcomeCheckpoint:
    """A single checkpoint measurement taken at a deferred interval."""
    checkpoint_type: str  # "24h" | "7d"
    timestamp: str = ""
    platform_metrics: Dict[str, Any] = field(default_factory=dict)
    behavior_signals: Dict[str, Any] = field(default_factory=dict)
    feedback_signals: Dict[str, Any] = field(default_factory=dict)
    composite_signal: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_type": self.checkpoint_type,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "platform_metrics": self.platform_metrics,
            "behavior_signals": self.behavior_signals,
            "feedback_signals": self.feedback_signals,
            "composite_signal": self.composite_signal,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> OutcomeCheckpoint:
        return cls(
            checkpoint_type=d.get("checkpoint_type", ""),
            timestamp=d.get("timestamp", ""),
            platform_metrics=d.get("platform_metrics", {}),
            behavior_signals=d.get("behavior_signals", {}),
            feedback_signals=d.get("feedback_signals", {}),
            composite_signal=d.get("composite_signal"),
            notes=d.get("notes", ""),
        )


@dataclass
class PendingOutcome:
    """A prediction awaiting real-world outcome resolution."""
    prediction_id: str = ""
    tracking_id: str = ""

    skill_name: str = ""
    client_id: str = ""
    channel_id: str = ""
    module_id: str = ""
    run_id: str = ""
    node_id: str = ""

    prediction: Dict[str, Any] = field(default_factory=dict)
    generation_score: Optional[float] = None
    delivery_metadata: Dict[str, Any] = field(default_factory=dict)
    platform_config: Dict[str, Any] = field(default_factory=dict)

    checkpoints: List[OutcomeCheckpoint] = field(default_factory=list)
    status: str = "pending"  # pending | checkpoint_24h | checkpoint_7d | closed | expired

    projection_classification: Optional[str] = None  # under_projection | over_projection | accurate_projection
    composite_score: Optional[float] = None

    created_at: str = ""
    due_24h: str = ""
    due_7d: str = ""
    closed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "tracking_id": self.tracking_id,
            "skill_name": self.skill_name,
            "client_id": self.client_id,
            "channel_id": self.channel_id,
            "module_id": self.module_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "prediction": self.prediction,
            "generation_score": self.generation_score,
            "delivery_metadata": self.delivery_metadata,
            "platform_config": self.platform_config,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "status": self.status,
            "projection_classification": self.projection_classification,
            "composite_score": self.composite_score,
            "created_at": self.created_at,
            "due_24h": self.due_24h,
            "due_7d": self.due_7d,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> PendingOutcome:
        checkpoints = [
            OutcomeCheckpoint.from_dict(c)
            for c in d.get("checkpoints", [])
        ]
        return cls(
            prediction_id=d.get("prediction_id", ""),
            tracking_id=d.get("tracking_id", ""),
            skill_name=d.get("skill_name", ""),
            client_id=d.get("client_id", ""),
            channel_id=d.get("channel_id", ""),
            module_id=d.get("module_id", ""),
            run_id=d.get("run_id", ""),
            node_id=d.get("node_id", ""),
            prediction=d.get("prediction", {}),
            generation_score=d.get("generation_score"),
            delivery_metadata=d.get("delivery_metadata", {}),
            platform_config=d.get("platform_config", {}),
            checkpoints=checkpoints,
            status=d.get("status", "pending"),
            projection_classification=d.get("projection_classification"),
            composite_score=d.get("composite_score"),
            created_at=d.get("created_at", ""),
            due_24h=d.get("due_24h", ""),
            due_7d=d.get("due_7d", ""),
            closed_at=d.get("closed_at"),
        )


class PendingOutcomeStore:
    """
    Firebase-backed store for predictions awaiting deferred outcome resolution.

    Predictions are registered when a skill completes execution and are resolved
    via checkpoints at 24h (adoption) and 7d (performance). The store tracks
    the full lifecycle from pending through closure or expiration.
    """

    _COLLECTION_BASE = "system/intelligence/pending_outcomes"

    def __init__(self, firebase_client: Any):
        self._firebase = firebase_client
        self._lock = threading.RLock()

    def _collection_path(self, client_id: str) -> str:
        return f"{self._COLLECTION_BASE}/{client_id}"

    def register(
        self,
        prediction_id: str,
        tracking_id: str,
        prediction: Dict[str, Any],
        execution_context: Dict[str, Any],
        delivery_metadata: Dict[str, Any],
        generation_score: Optional[float] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        channel_id: str = "",
        channel_config: Optional[Any] = None,
    ) -> PendingOutcome:
        """
        Register a new pending outcome after skill execution.

        Args:
            prediction_id: The intelligence system's prediction ID.
            tracking_id: The bridge's tracking ID.
            prediction: Full Prediction dict for deferred resolution.
            execution_context: Must include client_id, module_id, run_id,
                node_id, skill_name.
            delivery_metadata: Measurable identifiers extracted from outputs.
            generation_score: Immediate validation_score (diagnostic only).
            platform_config: Which retrieval module/credentials to use.
            channel_id: Marketing channel identifier (e.g. "email.lifecycle").
            channel_config: Optional ChannelConfig whose measurement_window_hours
                and full_measurement_days override the default 24h/7d schedule.
        """
        now = datetime.now(timezone.utc)
        client_id = execution_context.get("client_id", "unknown")

        # Use channel-specific measurement windows when available
        window_24h = timedelta(hours=24)
        window_7d = timedelta(days=7)
        if channel_config is not None:
            mw = getattr(channel_config, "measurement_window_hours", None)
            fm = getattr(channel_config, "full_measurement_days", None)
            if mw is not None:
                window_24h = timedelta(hours=mw)
            if fm is not None:
                window_7d = timedelta(days=fm)

        pending = PendingOutcome(
            prediction_id=prediction_id,
            tracking_id=tracking_id,
            skill_name=execution_context.get("skill_name", ""),
            client_id=client_id,
            channel_id=channel_id,
            module_id=execution_context.get("module_id", ""),
            run_id=execution_context.get("run_id", ""),
            node_id=execution_context.get("node_id", ""),
            prediction=prediction,
            generation_score=generation_score,
            delivery_metadata=delivery_metadata,
            platform_config=platform_config or {},
            status="pending",
            created_at=now.isoformat(),
            due_24h=(now + window_24h).isoformat(),
            due_7d=(now + window_7d).isoformat(),
        )

        with self._lock:
            try:
                self._firebase.set_document(
                    self._collection_path(client_id),
                    prediction_id,
                    pending.to_dict(),
                )
                logger.info(
                    f"Registered pending outcome {prediction_id} "
                    f"for {pending.skill_name} (client={client_id})"
                )
            except Exception as e:
                logger.error(f"Failed to register pending outcome: {e}")

        return pending

    def query_due(
        self,
        checkpoint_type: str,
        as_of: Optional[datetime] = None,
    ) -> List[PendingOutcome]:
        """
        Find all pending outcomes due for a given checkpoint type.

        Args:
            checkpoint_type: "24h" or "7d"
            as_of: Reference time (defaults to now UTC).
        """
        as_of = as_of or datetime.now(timezone.utc)
        as_of_iso = as_of.isoformat()

        if checkpoint_type == "24h":
            required_status = "pending"
            due_field = "due_24h"
        elif checkpoint_type == "7d":
            required_status = "checkpoint_24h"
            due_field = "due_7d"
        else:
            logger.warning(f"Unknown checkpoint_type: {checkpoint_type}")
            return []

        results: List[PendingOutcome] = []
        with self._lock:
            try:
                all_clients = self._firebase.get_collection(self._COLLECTION_BASE)
                if not all_clients:
                    return results

                client_ids = set()
                for doc in all_clients:
                    cid = doc.get("client_id")
                    if cid:
                        client_ids.add(cid)

                for client_id in client_ids:
                    try:
                        docs = self._firebase.query(
                            self._collection_path(client_id),
                            filters=[("status", "==", required_status)],
                        )
                        for doc in (docs or []):
                            d = doc if isinstance(doc, dict) else (
                                doc.to_dict() if hasattr(doc, "to_dict") else {}
                            )
                            due_val = d.get(due_field, "")
                            if due_val and due_val <= as_of_iso:
                                results.append(PendingOutcome.from_dict(d))
                    except Exception as e:
                        logger.debug(f"Query failed for client {client_id}: {e}")

            except Exception as e:
                logger.error(f"Failed to query due outcomes: {e}")

        return results

    def get(self, client_id: str, prediction_id: str) -> Optional[PendingOutcome]:
        """Load a single pending outcome by client and prediction ID."""
        with self._lock:
            try:
                doc = self._firebase.get_document(
                    self._collection_path(client_id), prediction_id
                )
                if doc:
                    return PendingOutcome.from_dict(doc)
            except Exception as e:
                logger.debug(f"Failed to get pending outcome {prediction_id}: {e}")
        return None

    def record_checkpoint(
        self,
        client_id: str,
        prediction_id: str,
        checkpoint: OutcomeCheckpoint,
    ) -> bool:
        """
        Record a checkpoint measurement and advance the status.

        For 24h checkpoints: status advances from pending -> checkpoint_24h.
        For 7d checkpoints: status advances from checkpoint_24h -> checkpoint_7d.
        """
        with self._lock:
            try:
                pending = self.get(client_id, prediction_id)
                if not pending:
                    logger.warning(f"Pending outcome {prediction_id} not found")
                    return False

                checkpoint.timestamp = checkpoint.timestamp or datetime.now(
                    timezone.utc
                ).isoformat()
                pending.checkpoints.append(checkpoint)

                if checkpoint.checkpoint_type == "24h":
                    pending.status = "checkpoint_24h"
                elif checkpoint.checkpoint_type == "7d":
                    pending.status = "checkpoint_7d"

                self._firebase.set_document(
                    self._collection_path(client_id),
                    prediction_id,
                    pending.to_dict(),
                )
                logger.info(
                    f"Recorded {checkpoint.checkpoint_type} checkpoint for {prediction_id}"
                )
                return True
            except Exception as e:
                logger.error(f"Failed to record checkpoint: {e}")
                return False

    def close(
        self,
        client_id: str,
        prediction_id: str,
        composite_score: float,
        projection_classification: str,
    ) -> Optional[PendingOutcome]:
        """
        Close a pending outcome after 7d checkpoint with final scores.

        Returns the closed PendingOutcome for downstream processing
        (feeding into the learning loop).
        """
        with self._lock:
            try:
                pending = self.get(client_id, prediction_id)
                if not pending:
                    logger.warning(f"Pending outcome {prediction_id} not found for close")
                    return None

                pending.status = "closed"
                pending.composite_score = composite_score
                pending.projection_classification = projection_classification
                pending.closed_at = datetime.now(timezone.utc).isoformat()

                self._firebase.set_document(
                    self._collection_path(client_id),
                    prediction_id,
                    pending.to_dict(),
                )
                logger.info(
                    f"Closed outcome {prediction_id}: "
                    f"{projection_classification} (score={composite_score:.3f})"
                )
                return pending
            except Exception as e:
                logger.error(f"Failed to close outcome: {e}")
                return None

    def expire_stale(self, max_age_days: int = 14) -> int:
        """
        Expire pending outcomes older than max_age_days that were never
        resolved. Returns count of expired outcomes.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ).isoformat()
        expired_count = 0

        with self._lock:
            try:
                all_docs = self._firebase.get_collection(self._COLLECTION_BASE)
                if not all_docs:
                    return 0

                client_ids = {d.get("client_id") for d in all_docs if d.get("client_id")}
                for client_id in client_ids:
                    try:
                        docs = self._firebase.query(
                            self._collection_path(client_id),
                            filters=[("status", "in", ["pending", "checkpoint_24h"])],
                        )
                        for doc in (docs or []):
                            d = doc if isinstance(doc, dict) else (
                                doc.to_dict() if hasattr(doc, "to_dict") else {}
                            )
                            created = d.get("created_at", "")
                            pid = d.get("prediction_id", "")
                            if created and created < cutoff and pid:
                                self._firebase.set_document(
                                    self._collection_path(client_id),
                                    pid,
                                    {"status": "expired", "closed_at": datetime.now(timezone.utc).isoformat()},
                                    merge=True,
                                )
                                expired_count += 1
                    except Exception as e:
                        logger.debug(f"Expire scan failed for {client_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to expire stale outcomes: {e}")

        if expired_count:
            logger.info(f"Expired {expired_count} stale pending outcomes")
        return expired_count

    def list_closed(
        self,
        client_id: Optional[str] = None,
        since_days: int = 30,
        limit: int = 100,
    ) -> List[PendingOutcome]:
        """
        List closed outcomes for analysis (used by the improvement engine).
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=since_days)
        ).isoformat()
        results: List[PendingOutcome] = []

        with self._lock:
            try:
                if client_id:
                    client_ids = [client_id]
                else:
                    all_docs = self._firebase.get_collection(self._COLLECTION_BASE)
                    client_ids = list({
                        d.get("client_id") for d in (all_docs or []) if d.get("client_id")
                    })

                for cid in client_ids:
                    try:
                        docs = self._firebase.query(
                            self._collection_path(cid),
                            filters=[("status", "==", "closed")],
                            limit=limit,
                        )
                        for doc in (docs or []):
                            d = doc if isinstance(doc, dict) else (
                                doc.to_dict() if hasattr(doc, "to_dict") else {}
                            )
                            if d.get("closed_at", "") >= cutoff:
                                results.append(PendingOutcome.from_dict(d))
                    except Exception as e:
                        logger.debug(f"List closed failed for {cid}: {e}")
            except Exception as e:
                logger.error(f"Failed to list closed outcomes: {e}")

        results.sort(key=lambda p: p.closed_at or "", reverse=True)
        return results[:limit]


__all__ = ["PendingOutcomeStore", "PendingOutcome", "OutcomeCheckpoint"]
