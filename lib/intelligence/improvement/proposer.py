"""
MH1 Improvement Proposer

Generates concrete improvement proposals from ImprovementCandidate
patterns. Each proposal specifies a target (skill, agent, or template)
and the proposed changes, along with evidence from the under-projection
analysis.

Proposal types:
    skill_update     — Modify an existing SKILL.md or its scripts
    agent_training   — Add training examples or approach notes to agent persona
    template_revision — Update output templates
    new_skill        — Create a new skill via skill-builder
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analyzer import ImprovementCandidate

logger = logging.getLogger(__name__)


@dataclass
class ImprovementProposal:
    """A concrete, actionable improvement proposal."""
    proposal_id: str = ""
    candidate_id: str = ""
    proposal_type: str = ""  # skill_update | agent_training | template_revision | new_skill
    target_path: str = ""
    skill_name: str = ""
    title: str = ""
    description: str = ""
    evidence_summary: str = ""
    proposed_changes: str = ""
    severity: float = 0.0
    status: str = "pending"  # pending | approved | rejected | applied
    created_at: str = ""
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "candidate_id": self.candidate_id,
            "proposal_type": self.proposal_type,
            "target_path": self.target_path,
            "skill_name": self.skill_name,
            "title": self.title,
            "description": self.description,
            "evidence_summary": self.evidence_summary,
            "proposed_changes": self.proposed_changes,
            "severity": self.severity,
            "status": self.status,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ImprovementProposal:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ImprovementProposer:
    """
    Generates improvement proposals from analyzed improvement candidates.

    Maps pattern types to proposal types:
        under_projection  → skill_update or new_skill
        negative_feedback → agent_training or template_revision
        heavy_editing     → agent_training (voice/tone mismatch)
    """

    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root or Path("/Applications/MH1/mh1-hq")

    def propose(
        self, candidates: List[ImprovementCandidate]
    ) -> List[ImprovementProposal]:
        """Generate proposals for each improvement candidate.

        Gathers external context for each candidate before generating
        proposals, enriching the evidence summary with temporal and
        cross-client failure patterns.
        """
        proposals: List[ImprovementProposal] = []
        now = datetime.now(timezone.utc).isoformat()

        for candidate in candidates:
            # Enrich candidate with external context
            external_ctx = self._gather_external_context(candidate)
            if external_ctx and external_ctx != "No external context available":
                candidate.pattern_description += f"\n\nExternal context:\n{external_ctx}"

            if candidate.pattern_type == "under_projection":
                proposals.extend(self._propose_for_under_projection(candidate, now))
            elif candidate.pattern_type == "negative_feedback":
                proposals.extend(self._propose_for_negative_feedback(candidate, now))
            elif candidate.pattern_type == "heavy_editing":
                proposals.extend(self._propose_for_heavy_editing(candidate, now))

        return proposals

    def _propose_for_under_projection(
        self, candidate: ImprovementCandidate, now: str
    ) -> List[ImprovementProposal]:
        """Under-projection: skill needs better strategies or missing capabilities."""
        proposals: List[ImprovementProposal] = []
        skill_path = self._find_skill_path(candidate.skill_name)

        if skill_path:
            proposals.append(ImprovementProposal(
                proposal_id=f"prop_{candidate.candidate_id}_skill",
                candidate_id=candidate.candidate_id,
                proposal_type="skill_update",
                target_path=skill_path,
                skill_name=candidate.skill_name,
                title=f"Update {candidate.skill_name} for better {candidate.domain} outcomes",
                description=(
                    f"The skill {candidate.skill_name} has {candidate.consecutive_count} "
                    f"consecutive under-projections for {candidate.domain} domain. "
                    f"Average delta: {candidate.avg_delta:.3f}. "
                    f"The skill's strategies may need updating for current market conditions."
                ),
                evidence_summary=self._summarize_evidence(candidate),
                proposed_changes=(
                    f"Review SKILL.md for {candidate.skill_name} and update:\n"
                    f"- Strategy templates and frameworks\n"
                    f"- Analysis depth for {candidate.domain} metrics\n"
                    f"- Output format to better match client expectations\n"
                    f"- Consider adding domain-specific stages"
                ),
                severity=candidate.severity,
                created_at=now,
            ))
        else:
            proposals.append(ImprovementProposal(
                proposal_id=f"prop_{candidate.candidate_id}_new",
                candidate_id=candidate.candidate_id,
                proposal_type="new_skill",
                target_path=f"skills/*/{candidate.skill_name}/SKILL.md",
                skill_name=candidate.skill_name,
                title=f"Create specialized variant of {candidate.skill_name}",
                description=(
                    f"No existing skill found at expected path. "
                    f"Consider creating a new skill via skill-builder."
                ),
                evidence_summary=self._summarize_evidence(candidate),
                proposed_changes="Use skill-builder to create a new skill variant.",
                severity=candidate.severity,
                created_at=now,
            ))

        return proposals

    def _propose_for_negative_feedback(
        self, candidate: ImprovementCandidate, now: str
    ) -> List[ImprovementProposal]:
        """Negative feedback: agent voice or template structure mismatch."""
        return [ImprovementProposal(
            proposal_id=f"prop_{candidate.candidate_id}_agent",
            candidate_id=candidate.candidate_id,
            proposal_type="agent_training",
            target_path=self._find_agent_path(candidate.skill_name),
            skill_name=candidate.skill_name,
            title=f"Improve agent training for {candidate.skill_name}",
            description=(
                f"Client feedback is consistently negative for {candidate.skill_name} "
                f"({candidate.pattern_description}). "
                f"The agent persona may need additional training examples or "
                f"approach modifications."
            ),
            evidence_summary=self._summarize_evidence(candidate),
            proposed_changes=(
                f"Add training examples to agent persona:\n"
                f"- Include examples of client-preferred output style\n"
                f"- Add domain-specific expertise notes\n"
                f"- Update approach section with lessons from feedback"
            ),
            severity=candidate.severity,
            created_at=now,
        )]

    def _propose_for_heavy_editing(
        self, candidate: ImprovementCandidate, now: str
    ) -> List[ImprovementProposal]:
        """Heavy editing: content doesn't match client voice/expectations."""
        return [ImprovementProposal(
            proposal_id=f"prop_{candidate.candidate_id}_voice",
            candidate_id=candidate.candidate_id,
            proposal_type="agent_training",
            target_path=self._find_agent_path(candidate.skill_name),
            skill_name=candidate.skill_name,
            title=f"Fix voice/tone mismatch for {candidate.skill_name}",
            description=(
                f"Outputs from {candidate.skill_name} are consistently heavily edited "
                f"by clients ({candidate.pattern_description}). "
                f"This suggests a voice or tone mismatch between agent output and "
                f"client expectations."
            ),
            evidence_summary=self._summarize_evidence(candidate),
            proposed_changes=(
                f"Update agent persona and skill configuration:\n"
                f"- Strengthen voice matching in agent persona\n"
                f"- Add client-specific writing samples as training data\n"
                f"- Review and update output templates for tone alignment\n"
                f"- Consider extracting more voice samples via extract-founder-voice"
            ),
            severity=candidate.severity,
            created_at=now,
        )]

    def _find_skill_path(self, skill_name: str) -> str:
        """Find the SKILL.md path for a skill name."""
        skills_dir = self._project_root / "skills"
        if not skills_dir.exists():
            return ""
        for category in skills_dir.iterdir():
            if not category.is_dir():
                continue
            skill_dir = category / skill_name
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                return str(skill_md.relative_to(self._project_root))
        return ""

    def _find_agent_path(self, skill_name: str) -> str:
        """Best-effort agent path for a skill."""
        agents_dir = self._project_root / "agents" / "workers"
        if agents_dir.exists():
            for agent_file in agents_dir.iterdir():
                if skill_name.split("-")[0] in agent_file.name.lower():
                    return str(agent_file.relative_to(self._project_root))
        return f"agents/workers/{skill_name}"

    def _gather_external_context(
        self, candidate: ImprovementCandidate, lookback_days: int = 14
    ) -> str:
        """Gather external context to inform the proposal.

        Checks episode context for failure patterns and temporal clustering.
        Stub-ready for MH-OS API integration when available.
        """
        context_parts: List[str] = []

        # Episode-level context from failure evidence
        for evidence in candidate.evidence:
            if isinstance(evidence, dict):
                ctx = evidence.get("context", {})
                if ctx:
                    context_parts.append(f"Episode context: {ctx}")

        # Temporal pattern in failures
        dates = [
            e.get("closed_at", "")[:10]
            for e in candidate.evidence
            if isinstance(e, dict) and e.get("closed_at")
        ]
        if dates:
            unique_dates = sorted(set(dates))
            context_parts.append(f"Failure dates: {', '.join(unique_dates)}")
            if len(unique_dates) >= 2:
                context_parts.append(
                    f"Failure date spread: {unique_dates[0]} to {unique_dates[-1]}"
                )

        # Client segments in failures
        clients = [
            e.get("client_id", "")
            for e in candidate.evidence
            if isinstance(e, dict) and e.get("client_id")
        ]
        if clients:
            unique_clients = sorted(set(clients))
            context_parts.append(f"Affected clients: {', '.join(unique_clients[:5])}")

        # MH-OS integration stub (ready for merge)
        # When MH-OS API is available:
        # mh_os_signals = mh_os_client.get_signals(
        #     source="daily-pulse",
        #     date_range=(start_date, end_date),
        #     filters={"skill": candidate.skill_name},
        # )
        # context_parts.append(f"Business signals: {mh_os_signals}")

        return "\n".join(context_parts) or "No external context available"

    def _summarize_evidence(self, candidate: ImprovementCandidate) -> str:
        """Create a brief evidence summary from the candidate."""
        parts = [
            f"Pattern: {candidate.pattern_type}",
            f"Skill: {candidate.skill_name}",
            f"Domain: {candidate.domain}",
            f"Severity: {candidate.severity:.2f}",
        ]
        if candidate.evidence:
            parts.append(f"Evidence items: {len(candidate.evidence)}")
            for ev in candidate.evidence[:3]:
                parts.append(f"  - {ev}")
        return "\n".join(parts)


__all__ = ["ImprovementProposer", "ImprovementProposal"]
