"""
MH1 Self-Improvement Engine

Analyzes closed outcomes for systematic under-projection patterns,
generates improvement proposals for skills/agents/templates, and
manages the review queue for human approval before deployment.

Components:
    ImprovementAnalyzer — Scan episodic memory for systematic patterns
    ImprovementProposer — Generate concrete improvement proposals
    ImprovementExecutor — Dispatch approved proposals (skill-builder, etc)
    ImprovementReviewer — Review queue management
"""

from .analyzer import ImprovementAnalyzer, ImprovementCandidate
from .proposer import ImprovementProposer, ImprovementProposal
from .executor import ImprovementExecutor
from .review import ImprovementReviewer

__all__ = [
    "ImprovementAnalyzer",
    "ImprovementCandidate",
    "ImprovementProposer",
    "ImprovementProposal",
    "ImprovementExecutor",
    "ImprovementReviewer",
]
