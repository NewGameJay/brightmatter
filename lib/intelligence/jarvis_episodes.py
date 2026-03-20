"""
Jarvis Episode Converter

Converts Jarvis-format episodes (TypeScript JarvisEpisode interface)
into BrightMatter-compatible EpisodicMemory objects for storage and
consolidation alongside skill execution episodes.

Jarvis episodes have:
  context: {trigger, query_summary, tools_used, providers_queried, topic_tags}
  outcome: {goal_completed, user_satisfaction, corrections, preferences_learned, metadata}

These are mapped to BrightMatter types:
  prediction.skill_name = "jarvis_interactive" | "jarvis_heartbeat"
  prediction.tenant_id  = "jarvis"
  prediction.domain     = Domain.GENERIC
  prediction.context    = jarvis context fields
  outcome.observed_signal = user_satisfaction (0-5 → 0.0-1.0)
  outcome.goal_completed  = goal_completed
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .types import Domain, EpisodeSource, EpisodicMemory, Outcome, Prediction


def jarvis_episode_to_episodic(
    raw: Dict[str, Any],
    tenant_id: str = "jarvis",
) -> EpisodicMemory:
    """Convert a Jarvis episode payload to a BrightMatter EpisodicMemory.

    Args:
        raw: Dict with keys ``context`` and ``outcome`` matching the
             Jarvis episode schema.
        tenant_id: Tenant for the episode (default ``"jarvis"``).

    Returns:
        An ``EpisodicMemory`` ready for ``episodic_store.store()``.
    """
    ctx = raw.get("context", {})
    out = raw.get("outcome", {})

    trigger = ctx.get("trigger", "interactive")
    skill_name = f"jarvis_{trigger}" if trigger else "jarvis_interactive"

    satisfaction = out.get("user_satisfaction", 3)  # 0-5 scale
    observed_signal = max(0.0, min(1.0, float(satisfaction) / 5.0))

    prediction_context: Dict[str, Any] = {
        "trigger": trigger,
        "query_summary": ctx.get("query_summary", ""),
        "tools_used": ctx.get("tools_used", []),
        "providers_queried": ctx.get("providers_queried", []),
        "topic_tags": ctx.get("topic_tags", []),
        "source": EpisodeSource.JARVIS_INTERACTION.value,
    }

    prediction = Prediction(
        prediction_id=str(uuid.uuid4())[:12],
        skill_name=skill_name,
        tenant_id=tenant_id,
        domain=Domain.GENERIC,
        expected_signal=0.6,
        expected_baseline=1.0,
        confidence=0.5,
        context=prediction_context,
    )

    outcome = Outcome(
        outcome_id=str(uuid.uuid4())[:12],
        prediction_id=prediction.prediction_id,
        observed_signal=observed_signal,
        observed_baseline=1.0,
        goal_completed=out.get("goal_completed", False),
        metadata={
            "corrections": out.get("corrections", []),
            "preferences_learned": out.get("preferences_learned", []),
            **(out.get("metadata", {})),
        },
    )

    now_iso = raw.get("timestamp", datetime.now(timezone.utc).isoformat())

    return EpisodicMemory(
        episode_id=raw.get("episode_id", str(uuid.uuid4())[:12]),
        prediction=prediction,
        outcome=outcome,
        weight=1.0,
        created_at=now_iso,
    )
