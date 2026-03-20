"""
MH1 Improvement Executor

Dispatches approved improvement proposals to the appropriate handler:
    skill_update / new_skill → skill-builder skill in a sandbox
    agent_training → append training data to agent persona files
    template_revision → generate updated template

All changes go to the Firebase review queue — nothing is auto-deployed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .proposer import ImprovementProposal

logger = logging.getLogger(__name__)


class ImprovementExecutor:
    """
    Dispatches approved improvement proposals.

    This executor does NOT auto-apply changes to the workspace.
    Instead, it generates the improvement artifacts and stores them
    in the Firebase review queue for human review.
    """

    def __init__(self, firebase_client: Any = None):
        self._firebase = firebase_client
        self._QUEUE_PATH = "system/intelligence/improvement_proposals"

    def dispatch(self, proposal: ImprovementProposal) -> Dict[str, Any]:
        """
        Dispatch a single approved proposal.

        Returns a result dict with status and any generated artifacts.
        """
        if proposal.status != "approved":
            return {"error": "Proposal must be approved before dispatch", "proposal_id": proposal.proposal_id}

        handler = {
            "skill_update": self._handle_skill_update,
            "new_skill": self._handle_new_skill,
            "agent_training": self._handle_agent_training,
            "template_revision": self._handle_template_revision,
        }.get(proposal.proposal_type)

        if not handler:
            return {"error": f"Unknown proposal type: {proposal.proposal_type}"}

        result = handler(proposal)

        # Update proposal status in Firebase
        self._update_proposal_status(
            proposal.proposal_id,
            status="dispatched",
            dispatch_result=result,
        )

        return result

    def _handle_skill_update(self, proposal: ImprovementProposal) -> Dict[str, Any]:
        """
        Queue a skill update for review.

        In production, this would invoke the skill-builder skill in a
        sandbox with the improvement context. For now, we store the
        proposal details so a human can make the changes.
        """
        logger.info(f"Queuing skill update for {proposal.skill_name}: {proposal.title}")
        return {
            "status": "queued",
            "action": "skill_update",
            "skill_name": proposal.skill_name,
            "target_path": proposal.target_path,
            "description": proposal.description,
            "proposed_changes": proposal.proposed_changes,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_new_skill(self, proposal: ImprovementProposal) -> Dict[str, Any]:
        """Queue a new skill creation via skill-builder."""
        logger.info(f"Queuing new skill creation: {proposal.skill_name}")
        return {
            "status": "queued",
            "action": "new_skill",
            "skill_name": proposal.skill_name,
            "description": proposal.description,
            "evidence": proposal.evidence_summary,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_agent_training(self, proposal: ImprovementProposal) -> Dict[str, Any]:
        """Queue agent training data updates."""
        logger.info(f"Queuing agent training for {proposal.skill_name}: {proposal.title}")
        return {
            "status": "queued",
            "action": "agent_training",
            "target_path": proposal.target_path,
            "skill_name": proposal.skill_name,
            "description": proposal.description,
            "proposed_changes": proposal.proposed_changes,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_template_revision(self, proposal: ImprovementProposal) -> Dict[str, Any]:
        """Queue template revision."""
        logger.info(f"Queuing template revision for {proposal.skill_name}")
        return {
            "status": "queued",
            "action": "template_revision",
            "target_path": proposal.target_path,
            "skill_name": proposal.skill_name,
            "description": proposal.description,
            "proposed_changes": proposal.proposed_changes,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

    def _update_proposal_status(
        self,
        proposal_id: str,
        status: str,
        dispatch_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update proposal status in Firebase."""
        if not self._firebase:
            return
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if dispatch_result:
                update_data["dispatch_result"] = dispatch_result
            self._firebase.set_document(
                self._QUEUE_PATH,
                proposal_id,
                update_data,
                merge=True,
            )
        except Exception as e:
            logger.debug(f"Failed to update proposal status: {e}")


__all__ = ["ImprovementExecutor"]
