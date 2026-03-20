"""
Three-Gate Resonance Scoring

Gates represent sequential validation of marketing output:
  Gate 1: Operator Resonance — Did the marketer adopt the strategy?
  Gate 2: Client Resonance — Did the client approve and implement?
  Gate 3: Market Resonance — Did the audience respond?

The compound of all three gates produces the learning signal.
Signal quality is weighted by parameter openness — more BrightMatter-generated
parameters means a cleaner attribution of outcome to recommendation.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParameterClassification:
    """Classification of a strategy parameter's source and mutability.

    Attributes:
        source: "locked" (client mandate, cannot change), "seeded" (BM
                suggestion that operator can override), or "open" (BM chose
                freely).
        origin: Who created the value — "client_mandate",
                "operator_preference", or "brightmatter_suggestion".
        was_overridden: True if operator changed BM's suggestion.
    """
    parameter_name: str
    source: str  # "locked" | "seeded" | "open"
    origin: str  # "client_mandate" | "operator_preference" | "brightmatter_suggestion"
    value: Any = None
    brightmatter_alternative: Optional[Any] = None
    was_overridden: bool = False
    override_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "source": self.source,
            "origin": self.origin,
            "value": self.value,
            "brightmatter_alternative": self.brightmatter_alternative,
            "was_overridden": self.was_overridden,
            "override_value": self.override_value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ParameterClassification:
        return cls(
            parameter_name=data.get("parameter_name", ""),
            source=data.get("source", "open"),
            origin=data.get("origin", "brightmatter_suggestion"),
            value=data.get("value"),
            brightmatter_alternative=data.get("brightmatter_alternative"),
            was_overridden=data.get("was_overridden", False),
            override_value=data.get("override_value"),
        )


@dataclass
class GateScore:
    """Score for a single resonance gate."""
    gate: str  # "operator" | "client" | "market"
    score: float  # 0.0 to 1.0
    signals: Dict[str, Any] = field(default_factory=dict)
    measured_at: Optional[str] = None
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "score": self.score,
            "signals": self.signals,
            "measured_at": self.measured_at,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GateScore:
        return cls(
            gate=data.get("gate", ""),
            score=data.get("score", 0.0),
            signals=data.get("signals", {}),
            measured_at=data.get("measured_at"),
            confidence=data.get("confidence", 0.5),
        )


@dataclass
class ThreeGateScore:
    """Complete three-gate resonance score for a strategy/output."""
    tracking_id: str
    skill_name: str
    client_id: str
    channel_id: str  # e.g. "paid_social.meta", "email.lifecycle"

    parameters: List[ParameterClassification] = field(default_factory=list)
    openness_ratio: float = 0.0

    gate_1_operator: Optional[GateScore] = None
    gate_2_client: Optional[GateScore] = None
    gate_3_market: Optional[GateScore] = None

    compound_score: float = 0.0
    learning_signal_quality: float = 0.0

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracking_id": self.tracking_id,
            "skill_name": self.skill_name,
            "client_id": self.client_id,
            "channel_id": self.channel_id,
            "parameters": [p.to_dict() for p in self.parameters],
            "openness_ratio": self.openness_ratio,
            "gate_1_operator": self.gate_1_operator.to_dict() if self.gate_1_operator else None,
            "gate_2_client": self.gate_2_client.to_dict() if self.gate_2_client else None,
            "gate_3_market": self.gate_3_market.to_dict() if self.gate_3_market else None,
            "compound_score": self.compound_score,
            "learning_signal_quality": self.learning_signal_quality,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ThreeGateScore:
        params = [ParameterClassification.from_dict(p) for p in data.get("parameters", [])]
        g1 = GateScore.from_dict(data["gate_1_operator"]) if data.get("gate_1_operator") else None
        g2 = GateScore.from_dict(data["gate_2_client"]) if data.get("gate_2_client") else None
        g3 = GateScore.from_dict(data["gate_3_market"]) if data.get("gate_3_market") else None
        return cls(
            tracking_id=data.get("tracking_id", ""),
            skill_name=data.get("skill_name", ""),
            client_id=data.get("client_id", ""),
            channel_id=data.get("channel_id", ""),
            parameters=params,
            openness_ratio=data.get("openness_ratio", 0.0),
            gate_1_operator=g1,
            gate_2_client=g2,
            gate_3_market=g3,
            compound_score=data.get("compound_score", 0.0),
            learning_signal_quality=data.get("learning_signal_quality", 0.0),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
        )


def _sigmoid(x: float, midpoint: float = 0.5, steepness: float = 10.0) -> float:
    """Sigmoid normalization mapping [0, 1] input to [0, 1] with configurable curve."""
    try:
        return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))
    except OverflowError:
        return 0.0 if x < midpoint else 1.0


class ThreeGateScorer:
    """Computes gate scores from raw signals.

    Gate weights default to 25% / 25% / 50% (market resonance
    is the strongest signal that the strategy actually worked).
    """

    GATE_WEIGHTS = {"operator": 0.25, "client": 0.25, "market": 0.50}

    def score_gate_1(self, signals: Dict[str, Any]) -> GateScore:
        """Gate 1: Operator Resonance — did the marketer adopt the output?

        Key signals:
            edit_distance: 0.0 (no edits) to 1.0 (complete rewrite)
            time_to_review_hours: elapsed time from delivery to first edit
            sections_modified: count of sections changed
            parameters_overridden: count of BM suggestions changed
            adopted_without_changes: boolean
        """
        if signals.get("adopted_without_changes"):
            raw = 1.0
        else:
            edit_dist = signals.get("edit_distance", 0.5)
            adoption = 1.0 - min(1.0, edit_dist)

            overrides = signals.get("parameters_overridden", 0)
            override_penalty = min(1.0, overrides * 0.15)
            adoption *= (1.0 - override_penalty)

            time_hrs = signals.get("time_to_review_hours", 24)
            speed_bonus = max(0.0, 1.0 - (time_hrs / 48.0)) * 0.1
            raw = min(1.0, adoption + speed_bonus)

        score = _sigmoid(raw, midpoint=0.5, steepness=8.0)
        confidence = 0.8 if "edit_distance" in signals else 0.4

        return GateScore(
            gate="operator",
            score=score,
            signals=signals,
            measured_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
        )

    def score_gate_2(self, signals: Dict[str, Any]) -> GateScore:
        """Gate 2: Client Resonance — did the client approve and implement?

        Key signals:
            approval_rounds: number of revision cycles (1 = first-pass)
            revision_count: total revisions requested
            sentiment: -1.0 to 1.0 from feedback text
            implementation_fidelity: 0-1 how closely implementation matches strategy
            time_to_approval_hours: speed of approval
        """
        approval_rounds = signals.get("approval_rounds", 2)
        approval_score = max(0.0, 1.0 - (approval_rounds - 1) * 0.25)

        sentiment = signals.get("sentiment", 0.0)
        sentiment_norm = (sentiment + 1.0) / 2.0

        fidelity = signals.get("implementation_fidelity", 0.5)

        raw = 0.4 * approval_score + 0.3 * sentiment_norm + 0.3 * fidelity
        score = _sigmoid(raw, midpoint=0.5, steepness=8.0)
        confidence = 0.7 if "implementation_fidelity" in signals else 0.3

        return GateScore(
            gate="client",
            score=score,
            signals=signals,
            measured_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
        )

    def score_gate_3(
        self,
        signals: Dict[str, Any],
        channel_config: Optional[Any] = None,
    ) -> GateScore:
        """Gate 3: Market Resonance — did the audience respond?

        Channel-specific signals using the universal resonance formula
        parameterized by channel config (decay half-life, primary signal, etc.).
        Falls back to generic scoring when no config is provided.
        """
        primary_key = "primary_metric"
        baseline_key = "baseline"
        if channel_config is not None:
            primary_key = getattr(channel_config, "primary_signal", primary_key)
            baseline_key = f"{primary_key}_baseline"

        primary_value = signals.get(primary_key, signals.get("primary_metric", 0.0))
        baseline_value = signals.get(baseline_key, signals.get("baseline", 1.0))

        if baseline_value > 0:
            ratio = primary_value / baseline_value
        else:
            ratio = 1.0

        raw = min(2.0, ratio) / 2.0  # normalize [0, 2x baseline] → [0, 1]
        score = _sigmoid(raw, midpoint=0.5, steepness=6.0)

        sample_size = signals.get("sample_size", 0)
        min_sample = getattr(channel_config, "min_sample_size", 30) if channel_config else 30
        confidence = min(1.0, sample_size / min_sample) if min_sample > 0 else 0.5

        return GateScore(
            gate="market",
            score=score,
            signals=signals,
            measured_at=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
        )

    def compute_openness_ratio(
        self,
        parameters: List[ParameterClassification],
    ) -> float:
        """Fraction of parameters that were 'open' (BM chose freely)."""
        if not parameters:
            return 0.0
        open_count = sum(1 for p in parameters if p.source == "open")
        return open_count / len(parameters)

    def compute_compound(self, gate_score: ThreeGateScore) -> ThreeGateScore:
        """Compute compound score and learning signal quality.

        ``compound`` = weighted average of available gates.
        ``learning_signal_quality`` = compound × openness_ratio × gate_completeness.

        A strategy with all 3 gates measured, 80 % open parameters, and
        strong market performance gives the cleanest learning signal.
        """
        weighted_sum = 0.0
        weight_total = 0.0
        gates_present = 0

        for gate, weight in self.GATE_WEIGHTS.items():
            gs: Optional[GateScore] = getattr(gate_score, f"gate_{['operator', 'client', 'market'].index(gate) + 1}_{gate}", None)
            if gs is not None:
                weighted_sum += gs.score * gs.confidence * weight
                weight_total += weight * gs.confidence
                gates_present += 1

        compound = weighted_sum / weight_total if weight_total > 0 else 0.0

        gate_completeness = gates_present / 3.0
        openness = gate_score.openness_ratio

        gate_score.compound_score = compound
        gate_score.learning_signal_quality = compound * openness * gate_completeness

        if gates_present == 3:
            gate_score.completed_at = datetime.now(timezone.utc).isoformat()

        return gate_score
