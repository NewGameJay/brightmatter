"""
MH1 Deferred Outcome Tracking

Tracks real-world outcomes of skill executions via deferred checkpoints
at 24h (adoption) and 7d (performance), then feeds composite signals
back into the intelligence learning loop.

Components:
    PendingOutcomeStore — Firebase-backed store for open predictions
    CompositeSignalComputer — Score outcomes from platform + feedback signals
"""

from .pending_store import PendingOutcomeStore, PendingOutcome, OutcomeCheckpoint
from .signal_computer import CompositeSignalComputer, CompositeSignal

__all__ = [
    "PendingOutcomeStore",
    "PendingOutcome",
    "OutcomeCheckpoint",
    "CompositeSignalComputer",
    "CompositeSignal",
]
