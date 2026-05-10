"""Shared dataclasses for disconfirmation harnesses.

Each detector's harness imports `TestResult` and `SignalAudit` from here so
the per-detector module can focus on tests, not boilerplate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["confirm", "disconfirm", "inconclusive"]


@dataclass
class TestResult:
    test_id: str
    test_name: str
    verdict: Verdict
    summary: str
    evidence: list[dict] = field(default_factory=list)


@dataclass
class SignalAudit:
    """Result of running a harness against one fired signal.

    Per-detector audits may attach extra fields (campaign_id, business_type,
    brand_tokens_used, etc.) — the CLI uses getattr to render whatever is set.
    """
    signal_id: str
    account_id: str
    account_name: str
    detector_message: str
    detector_data: dict
    test_results: list[TestResult] = field(default_factory=list)
    # Optional metadata — set by per-detector audits when relevant.
    campaign_id: str | None = None
    business_type: str | None = None
    brand_tokens_used: list[str] | None = None

    @property
    def verdict_counts(self) -> dict[str, int]:
        c = {"confirm": 0, "disconfirm": 0, "inconclusive": 0}
        for r in self.test_results:
            c[r.verdict] += 1
        return c

    @property
    def overall(self) -> str:
        c = self.verdict_counts
        if c["disconfirm"] >= 2:
            return "likely_false_positive"
        if c["disconfirm"] == 1 and c["confirm"] >= 2:
            return "confirmed_with_caveat"
        if c["confirm"] >= 3 and c["disconfirm"] == 0:
            return "well_supported"
        if c["confirm"] >= 2 and c["disconfirm"] == 0:
            return "supported"
        return "weak_evidence"
