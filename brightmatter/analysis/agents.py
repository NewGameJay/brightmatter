"""Layer 2: LLM analysis agents — three personas with research docs as context.

Agent 1: Account Auditor — per-account health assessment
Agent 2: Pattern Spotter — cross-account pattern recognition
Agent 3: Signal Interpreter — root-cause diagnosis of anomalies

Each agent receives structured data as input and produces structured output.
Research docs are loaded from research/ and injected into system prompts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from brightmatter.config import RESEARCH_DIR, anthropic

logger = logging.getLogger("brightmatter.analysis")


# ── Structured output schemas ──

class AuditFinding(BaseModel):
    model_config = {"populate_by_name": True}
    domain: str = Field(default="general", alias="category")
    severity: str = "info"
    finding: str = Field(default="", alias="issue")
    evidence: str = Field(default="", alias="details")
    recommendation: str = Field(default="", alias="action")


class AccountAuditResult(BaseModel):
    model_config = {"populate_by_name": True}
    account_id: str = ""
    health_score: float = Field(default=50, ge=0, le=100, alias="overall_score")
    summary: str = ""
    findings: list[AuditFinding] = Field(default_factory=list)
    top_opportunity: str = Field(default="", alias="primary_opportunity")
    biggest_risk: str = Field(default="", alias="primary_issue")


class CrossAccountPattern(BaseModel):
    domain: str
    pattern_name: str
    description: str
    accounts_involved: list[str]
    confidence: float
    evidence: str
    actionability: str


class PatternSpotterResult(BaseModel):
    patterns_found: list[CrossAccountPattern] = Field(default_factory=list)
    summary: str = ""
    vertical_insights: str = ""


class DiagnosisResult(BaseModel):
    root_cause: str
    causal_chain: str
    confidence: float
    is_environmental: bool
    affected_scope: str
    recommended_response: str
    common_misdiagnosis: str
    evidence_summary: str


# ── Research doc loading ──

def _load_research(filenames: list[str]) -> str:
    """Load research markdown files and concatenate them for the system prompt."""
    parts = []
    for fname in filenames:
        path = _find_research_file(fname)
        if path and path.exists():
            content = path.read_text()
            if len(content) > 30000:
                content = content[:30000] + "\n\n[... truncated for context window ...]"
            parts.append(f"--- {fname} ---\n{content}")
        else:
            logger.warning("Research file not found: %s", fname)
    return "\n\n".join(parts)


def _find_research_file(name: str) -> Path | None:
    """Search for a research file by name across subdirectories."""
    for p in RESEARCH_DIR.rglob(name):
        return p
    for p in RESEARCH_DIR.rglob(f"*{name}*"):
        return p
    return None


# ── System prompts ──

AUDITOR_SYSTEM = """You are BrightMatter's Account Auditor — an expert Google Ads analyst who evaluates
individual account health against industry best practices and benchmark data.

You receive an account's configuration, metrics, signals from automated detectors,
and change history. Your job is to produce a structured health assessment.

REFERENCE KNOWLEDGE (expert frameworks and benchmarks):
{research_context}

ANALYSIS RULES:
- Score accounts 0-100 based on configuration quality, performance vs benchmarks, and structural health
- Flag specific issues with severity levels (info/warning/critical)
- Every finding must cite evidence from the data provided
- Compare metrics against vertical-specific benchmarks from the research
- Identify the single biggest opportunity and the single biggest risk
- Be specific and quantitative — not "CPA is high" but "CPA of $45 is 2.3x the vertical average of $19.50"

You MUST respond with ONLY valid JSON using EXACTLY these field names:
{{
  "account_id": "string",
  "health_score": 0-100,
  "summary": "string",
  "findings": [
    {{"domain": "string", "severity": "info|warning|critical", "finding": "string", "evidence": "string", "recommendation": "string"}}
  ],
  "top_opportunity": "string",
  "biggest_risk": "string"
}}"""

SPOTTER_SYSTEM = """You are BrightMatter's Pattern Spotter — an analyst who looks across multiple Google Ads
accounts simultaneously to find patterns that are invisible at the single-account level.

You receive aggregate metrics across accounts, grouped by vertical, spend tier, and campaign type.
Your job is to find cross-account patterns.

REFERENCE KNOWLEDGE (pattern detection logic and thresholds):
{research_context}

WHAT TO LOOK FOR:
- Accounts in the same vertical with dramatically different performance — what's different about their config?
- Campaign structure patterns that correlate with performance (number of campaigns, bidding strategy mix, etc.)
- Metrics moving in the same direction across multiple accounts simultaneously (environmental signal)
- Configuration patterns: do accounts using strategy X consistently outperform those using strategy Y?
- Anomalies: accounts that deviate significantly from their vertical peers

OUTPUT RULES:
- Each pattern must involve 2+ accounts
- Include confidence score (0.0 to 1.0) based on strength of evidence
- Describe what's actionable about the pattern
- Distinguish between correlation and likely causation

Respond with valid JSON matching the PatternSpotterResult schema."""

INTERPRETER_SYSTEM = """You are BrightMatter's Signal Interpreter — a diagnostic specialist who determines
the root cause of performance anomalies and pattern shifts.

You receive signals from automated detectors, account context, and change history.
Your job is to run through the diagnostic hierarchy and determine the most likely root cause.

REFERENCE KNOWLEDGE (causal chain signatures):
{research_context}

DIAGNOSTIC HIERARCHY (check in this order):
1. Tracking/measurement break — conversions dropped across all campaigns? Clicks stable? → tracking issue
2. Conversion definition change — new conversion actions added/removed? → measurement shift, not performance
3. Auto-applied recommendations — changes by non-human actors? → revert and assess
4. Landing page/website change — CVR drop on specific URLs? → page issue
5. Platform/algorithm change — multiple accounts affected simultaneously? → environmental
6. Competitor change — Auction Insights shifts? → competitive response needed
7. Seasonality — YoY comparison normal? → seasonal, not a problem
8. Actual account issue — none of the above? → genuine performance problem requiring optimization

RULES:
- Always start at the top of the hierarchy — tracking breaks are the most common misdiagnosed issue
- If multiple accounts show the same signal, it's almost certainly environmental
- Quantify confidence (0.0 to 1.0) — low confidence means more investigation needed
- Name the common misdiagnosis so the user doesn't fall into that trap
- Recommend the correct response, not just the diagnosis

Respond with valid JSON matching the DiagnosisResult schema."""


# ── Agent execution ──

class AgentRunner:
    """Executes LLM agents with research context and structured output."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not anthropic.is_configured:
                raise RuntimeError("ANTHROPIC_API_KEY not set — cannot run LLM agents")
            import anthropic as anthropic_sdk
            self._client = anthropic_sdk.Anthropic(api_key=anthropic.api_key)
        return self._client

    @property
    def is_available(self) -> bool:
        return anthropic.is_configured

    def audit_account(self, account_data: dict[str, Any], signals: list[dict]) -> AccountAuditResult:
        """Run the Account Auditor agent on a single account."""
        research = _load_research([
            "tier1-expert-frameworks.md",
            "industry-benchmarks.md",
        ])
        system = AUDITOR_SYSTEM.format(research_context=research)
        user_msg = (
            f"Account data:\n```json\n{json.dumps(account_data, indent=2, default=str)}\n```\n\n"
            f"Automated detector signals:\n```json\n{json.dumps(signals, indent=2, default=str)}\n```\n\n"
            "Produce a health assessment as JSON."
        )
        return self._run(system, user_msg, AccountAuditResult)

    def spot_patterns(self, cross_account_data: dict[str, Any]) -> PatternSpotterResult:
        """Run the Pattern Spotter agent across all accounts."""
        research = _load_research([
            "pattern-detection-logic.md",
            "industry-benchmarks.md",
        ])
        system = SPOTTER_SYSTEM.format(research_context=research)
        user_msg = (
            f"Cross-account data:\n```json\n{json.dumps(cross_account_data, indent=2, default=str)}\n```\n\n"
            "Find cross-account patterns and respond as JSON."
        )
        return self._run(system, user_msg, PatternSpotterResult)

    def interpret_signals(self, signal_data: dict[str, Any], context: dict[str, Any]) -> DiagnosisResult:
        """Run the Signal Interpreter agent on detected anomalies."""
        research = _load_research([
            "causal-chain-signatures.md",
            "pattern-detection-logic.md",
        ])
        system = INTERPRETER_SYSTEM.format(research_context=research)
        user_msg = (
            f"Signals to diagnose:\n```json\n{json.dumps(signal_data, indent=2, default=str)}\n```\n\n"
            f"Account context:\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
            "Diagnose the root cause and respond as JSON."
        )
        return self._run(system, user_msg, DiagnosisResult)

    def _run(self, system: str, user_msg: str, output_type: type[BaseModel]):
        """Execute a Claude API call and parse structured output."""
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text

        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            text = text[json_start:json_end]

        try:
            return output_type.model_validate_json(text)
        except Exception:
            # Try parsing as dict first to handle field name variations
            try:
                data = json.loads(text)
                return output_type.model_validate(data)
            except Exception:
                logger.error("Failed to parse agent response as %s: %s", output_type.__name__, text[:500])
                raise
