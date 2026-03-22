"""
MH-OS Signal Adapter

Converts MH-OS signal rows (from Supabase `signals` table) into
BrightMatter episodes. MH-OS signals contain daily-pulse and weekly
metrics for each client with deviation scoring and quality assessment.

Also converts MH-OS recommendation_feedback into outcome records
that close the learning loop.

Usage (in worker.py):
    from lib.intelligence.adapters.mh_os import signal_to_episode, feedback_to_outcome
    episode = signal_to_episode(signal_row)
    outcome = feedback_to_outcome(feedback_row)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


_LEVER_DOMAIN_MAP = {
    "paid-social": "campaign",
    "paid-search": "campaign",
    "email": "content",
    "lifecycle": "health",
    "retention": "health",
    "acquisition": "campaign",
    "revenue": "revenue",
    "organic-social": "content",
    "seo": "content",
    "crm": "health",
}


def _lever_to_domain(lever: str) -> str:
    """Map an MH-OS lever name to a BrightMatter domain."""
    if not lever:
        return "generic"
    normalized = lever.lower().replace("_", "-")
    return _LEVER_DOMAIN_MAP.get(normalized, "generic")


def _extract_primary_signal(metrics: Dict[str, Any]) -> float:
    """Extract a primary signal value from MH-OS metrics dict."""
    for key in ["primary_metric", "value", "deviation_score", "score", "pct_change"]:
        val = metrics.get(key)
        if val is not None and isinstance(val, (int, float)):
            return float(val)

    numeric_vals = [v for v in metrics.values() if isinstance(v, (int, float))]
    if numeric_vals:
        return numeric_vals[0]

    return 0.5


def signal_to_episode(signal_row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an MH-OS signal row into a BrightMatter episode dict.

    The returned dict can be passed to EpisodicMemory.from_dict() or
    used directly with the IntelligenceEngine.

    Args:
        signal_row: Row from the MH-OS `signals` Supabase table. Expected keys:
            - source: e.g., "daily-pulse", "weekly-report"
            - lever: e.g., "paid-social", "email", "retention"
            - client_id: client identifier
            - metrics: dict of metric values
            - cadence: "daily" or "weekly"
            - date: ISO date string
            - severity: "info", "warning", "critical"
    """
    source = signal_row.get("source", "mh-os-signal")
    lever = signal_row.get("lever", "")
    client_id = signal_row.get("client_id", "marketerhire")
    metrics = signal_row.get("metrics", {})
    cadence = signal_row.get("cadence", "daily")
    signal_date = signal_row.get("date", "")
    severity = signal_row.get("severity", "info")

    domain = _lever_to_domain(lever)
    primary_signal = _extract_primary_signal(metrics)

    return {
        "episode_id": f"mhos_{str(uuid.uuid4())[:8]}",
        "prediction": {
            "prediction_id": str(uuid.uuid4())[:12],
            "skill_name": source,
            "tenant_id": client_id,
            "domain": domain,
            "expected_signal": 0.5,
            "expected_baseline": 1.0,
            "context": {
                "lever": lever,
                "cadence": cadence,
                "signal_date": signal_date,
                "severity": severity,
                "metrics": metrics,
                "_episode_source": "market_observation",
            },
        },
        "outcome": {
            "prediction_id": str(uuid.uuid4())[:12],
            "observed_signal": primary_signal,
            "observed_baseline": 1.0,
            "goal_completed": severity != "critical",
            "metadata": {
                "_source": "mh-os",
                "_lever": lever,
                "_cadence": cadence,
                "_severity": severity,
                **metrics,
            },
        },
        "weight": 0.8 if severity == "info" else 1.0,
    }


def feedback_to_outcome(feedback_row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MH-OS recommendation_feedback into a BrightMatter outcome.

    Args:
        feedback_row: Row from `recommendation_feedback` table. Expected keys:
            - recommendation_id: ID of the recommendation
            - action: "approved", "denied", "modified"
            - rating: optional 1-5 rating
            - comment: optional text
            - client_id: client identifier
            - recommendation: the original recommendation dict
    """
    action = feedback_row.get("action", "")
    rating = feedback_row.get("rating")
    comment = feedback_row.get("comment", "")
    client_id = feedback_row.get("client_id", "")
    recommendation = feedback_row.get("recommendation", {})

    # Map action to signal
    action_signals = {
        "approved": 0.9,
        "modified": 0.6,
        "denied": 0.2,
    }
    observed_signal = action_signals.get(action, 0.5)

    if rating is not None:
        try:
            observed_signal = (float(rating) - 1.0) / 4.0
        except (TypeError, ValueError):
            pass

    return {
        "tracking_id": feedback_row.get("recommendation_id", ""),
        "source": "mh-os",
        "client_id": client_id,
        "outcome_type": "immediate",
        "observed_signal": observed_signal,
        "goal_completed": action == "approved",
        "feedback": {
            "action": action,
            "rating": rating,
            "comment": comment,
            "recommendation": recommendation,
            "_gate": "gate_1_operator" if action in ("approved", "denied") else "gate_2_client",
        },
    }


__all__ = [
    "signal_to_episode",
    "feedback_to_outcome",
]
