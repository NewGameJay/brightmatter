"""Pattern recorder — stores confirmed patterns from both detector layers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from brightmatter.models.patterns import Pattern, PatternDomain, PatternType, Severity, Signal
from brightmatter.storage.repository import Repository


class PatternRecorder:
    """Records patterns discovered by detectors and agents."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def record_from_signals(self, signals: list[Signal], detector: str = "deterministic") -> list[Pattern]:
        """Group related signals into patterns and record them."""
        grouped: dict[tuple[str, str], list[Signal]] = {}
        for s in signals:
            key = (s.domain.value, s.signal_type)
            grouped.setdefault(key, []).append(s)

        patterns = []
        for (domain, signal_type), sigs in grouped.items():
            accounts = list({s.account_id for s in sigs})
            severity = max(sigs, key=lambda s: _severity_rank(s.severity)).severity

            pattern_type = PatternType.THRESHOLD_VIOLATION
            if len(accounts) > 1:
                pattern_type = PatternType.CROSS_ACCOUNT

            pattern = Pattern(
                pattern_id=uuid.uuid4().hex[:12],
                domain=PatternDomain(domain),
                pattern_type=pattern_type,
                severity=severity,
                confidence=_confidence_from_count(len(sigs)),
                accounts_affected=accounts,
                summary=_summarize_signals(signal_type, sigs),
                evidence={"signals": [s.model_dump(mode="json") for s in sigs[:10]]},
                source_signals=[s.signal_id for s in sigs],
                detector=detector,
                detected_at=datetime.now(timezone.utc),
            )
            self.repo.insert_pattern(pattern)
            patterns.append(pattern)

        return patterns

    def record_pattern(self, pattern: Pattern) -> None:
        """Record a single pattern (typically from an LLM agent)."""
        self.repo.insert_pattern(pattern)


def _severity_rank(s: Severity) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(s.value, 0)


def _confidence_from_count(n: int) -> float:
    if n >= 5:
        return 0.9
    if n >= 3:
        return 0.75
    if n >= 2:
        return 0.6
    return 0.5


def _summarize_signals(signal_type: str, signals: list[Signal]) -> str:
    n = len(signals)
    accounts = len({s.account_id for s in signals})
    first = signals[0]

    if accounts > 1:
        return f"{signal_type}: {n} instances across {accounts} accounts — {first.message}"
    return f"{signal_type}: {n} instances in account {first.account_id} — {first.message}"
