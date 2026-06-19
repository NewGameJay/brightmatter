"""Pattern and signal models — the output of BrightMatter's analysis."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PatternDomain(str, Enum):
    """The 12 pattern domains from the research map."""

    BRANDED_SEARCH = "branded_search"
    NON_BRANDED_SEARCH = "non_branded_search"
    PERFORMANCE_MAX = "performance_max"
    VIDEO = "video"
    SHOPPING = "shopping"
    BIDDING_STRATEGY = "bidding_strategy"
    CAMPAIGN_STRUCTURE = "campaign_structure"
    SEO_PAID_INTERACTION = "seo_paid_interaction"
    LANDING_PAGE = "landing_page"
    SEASONALITY = "seasonality"
    CROSS_CHANNEL = "cross_channel"
    CREATIVE = "creative"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class PatternType(str, Enum):
    THRESHOLD_VIOLATION = "threshold_violation"
    CROSS_ACCOUNT = "cross_account"
    TEMPORAL = "temporal"
    ANOMALY = "anomaly"
    CONFIGURATION = "configuration"


class Signal(BaseModel):
    """A raw signal from a deterministic detector — Layer 1 output."""

    signal_id: str
    account_id: str
    campaign_id: str = ""
    domain: PatternDomain
    signal_type: str = ""
    severity: Severity = Severity.INFO
    value: float = 0.0
    threshold: float = 0.0
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    detected_at: Optional[datetime] = None
    # Confidence framework (analysis/confidence.py): every signal carries an
    # honest frame — what we proved, what we can't rule out, what to check.
    confidence_tier: str = ""          # CONFIRMED / LIKELY / SUGGESTIVE
    what_we_know: str = ""             # the factual finding (usually == message)
    what_we_cant_rule_out: str = ""    # alternative explanations we can't eliminate
    check_next: str = ""               # the specific thing for the marketer to verify
    # Phase 2.2 — temporal context from campaign_trends (set in a post-pass).
    trend_context: str = ""            # pre-existing decline / new development / normal fluctuation / no trend data
    trend_slope_30d: Optional[float] = None
    trend_classification_30d: str = ""


class Pattern(BaseModel):
    """A confirmed pattern from analysis — may span multiple accounts and signals."""

    pattern_id: str
    domain: PatternDomain
    pattern_type: PatternType = PatternType.THRESHOLD_VIOLATION
    severity: Severity = Severity.INFO
    confidence: float = 0.0
    accounts_affected: list[str] = Field(default_factory=list)
    summary: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_signals: list[str] = Field(default_factory=list)
    detector: str = ""
    detected_at: Optional[datetime] = None


class Diagnosis(BaseModel):
    """Root-cause diagnosis from the Signal Interpreter agent — Layer 2 output."""

    diagnosis_id: str
    pattern_id: str = ""
    signal_ids: list[str] = Field(default_factory=list)
    root_cause: str = ""
    causal_chain: str = ""
    confidence: float = 0.0
    is_environmental: bool = False
    affected_accounts: list[str] = Field(default_factory=list)
    recommended_response: str = ""
    common_misdiagnosis: str = ""
    diagnosed_at: Optional[datetime] = None
