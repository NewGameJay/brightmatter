"""
MH1 Improvement Review Queue

Manages the review queue for improvement proposals. Proposals are
stored in Firebase and must be approved by a human before they
take effect. Tracks which proposals were applied and whether they
improved outcomes (meta-learning on improvement effectiveness).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .proposer import ImprovementProposal

logger = logging.getLogger(__name__)


class ImprovementReviewer:
    """
    Manages the improvement proposal review queue in Firebase.

    Proposals flow through: pending -> approved/rejected -> dispatched -> applied
    """

    _QUEUE_PATH = "system/intelligence/improvement_proposals"

    def __init__(self, firebase_client: Any = None):
        self._firebase = firebase_client

    def submit(self, proposal: ImprovementProposal) -> bool:
        """Submit a proposal to the review queue."""
        if not self._firebase:
            logger.warning("Firebase not available — proposal not persisted")
            return False
        try:
            self._firebase.set_document(
                self._QUEUE_PATH,
                proposal.proposal_id,
                proposal.to_dict(),
            )
            logger.info(f"Submitted proposal {proposal.proposal_id}: {proposal.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to submit proposal: {e}")
            return False

    def list_pending(self, limit: int = 50) -> List[ImprovementProposal]:
        """List proposals awaiting review."""
        if not self._firebase:
            return []
        try:
            docs = self._firebase.query(
                self._QUEUE_PATH,
                filters=[("status", "==", "pending")],
                limit=limit,
            )
            return [
                ImprovementProposal.from_dict(
                    d if isinstance(d, dict) else d.to_dict()
                )
                for d in (docs or [])
            ]
        except Exception as e:
            logger.error(f"Failed to list pending proposals: {e}")
            return []

    def approve(
        self,
        proposal_id: str,
        approved_by: str = "human",
        notes: str = "",
    ) -> bool:
        """Approve a proposal for dispatch."""
        return self._update_status(proposal_id, "approved", approved_by, notes)

    def reject(
        self,
        proposal_id: str,
        rejected_by: str = "human",
        notes: str = "",
    ) -> bool:
        """Reject a proposal."""
        return self._update_status(proposal_id, "rejected", rejected_by, notes)

    def mark_applied(
        self,
        proposal_id: str,
        applied_by: str = "system",
        notes: str = "",
    ) -> bool:
        """Mark a proposal as applied to the workspace."""
        return self._update_status(proposal_id, "applied", applied_by, notes)

    def get_proposal(self, proposal_id: str) -> Optional[ImprovementProposal]:
        """Load a single proposal by ID."""
        if not self._firebase:
            return None
        try:
            doc = self._firebase.get_document(self._QUEUE_PATH, proposal_id)
            if doc:
                return ImprovementProposal.from_dict(doc)
        except Exception as e:
            logger.debug(f"Failed to get proposal {proposal_id}: {e}")
        return None

    def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ImprovementProposal]:
        """List proposals, optionally filtered by status."""
        if not self._firebase:
            return []
        try:
            filters = []
            if status:
                filters.append(("status", "==", status))
            docs = self._firebase.query(
                self._QUEUE_PATH,
                filters=filters if filters else None,
                limit=limit,
            )
            return [
                ImprovementProposal.from_dict(
                    d if isinstance(d, dict) else d.to_dict()
                )
                for d in (docs or [])
            ]
        except Exception as e:
            logger.error(f"Failed to list proposals: {e}")
            return []

    def get_stats(self) -> Dict[str, int]:
        """Get counts by status."""
        stats = {"pending": 0, "approved": 0, "rejected": 0, "applied": 0, "dispatched": 0}
        if not self._firebase:
            return stats
        try:
            for status in stats:
                docs = self._firebase.query(
                    self._QUEUE_PATH,
                    filters=[("status", "==", status)],
                    limit=1000,
                )
                stats[status] = len(docs or [])
        except Exception as e:
            logger.debug(f"Failed to get proposal stats: {e}")
        return stats

    def _update_status(
        self,
        proposal_id: str,
        status: str,
        by: str = "",
        notes: str = "",
    ) -> bool:
        """Update a proposal's status."""
        if not self._firebase:
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            self._firebase.set_document(
                self._QUEUE_PATH,
                proposal_id,
                {
                    "status": status,
                    "reviewed_at": now,
                    "reviewed_by": by,
                    "review_notes": notes,
                    "updated_at": now,
                },
                merge=True,
            )
            logger.info(f"Proposal {proposal_id} -> {status} by {by}")
            return True
        except Exception as e:
            logger.error(f"Failed to update proposal {proposal_id}: {e}")
            return False


__all__ = ["ImprovementReviewer"]
