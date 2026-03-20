"""
MH1 Deferred Outcome Tracking

Tracks real-world outcomes of skill executions via deferred checkpoints
at 24h (adoption) and 7d (performance), then feeds composite signals
back into the intelligence learning loop.

Components:
    PendingOutcomeStore — Firebase-backed store for open predictions
    DeliveryExtractor — Extract measurable identifiers from skill outputs
    CompositeSignalComputer — Score outcomes from platform + feedback + behavior
    BehaviorCollector — Query PostHog + Firebase for user behavior signals
"""

from .pending_store import PendingOutcomeStore, PendingOutcome, OutcomeCheckpoint
from .delivery_extractor import DeliveryExtractor, DeliveryMetadata
from .signal_computer import CompositeSignalComputer, CompositeSignal
from .behavior_collector import BehaviorCollector

__all__ = [
    "PendingOutcomeStore",
    "PendingOutcome",
    "OutcomeCheckpoint",
    "DeliveryExtractor",
    "DeliveryMetadata",
    "CompositeSignalComputer",
    "CompositeSignal",
    "BehaviorCollector",
]
