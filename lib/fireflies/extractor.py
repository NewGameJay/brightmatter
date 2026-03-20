"""
Fireflies ingestion — Insight Extractor

Uses Claude Haiku to extract structured insights from meeting transcripts
and detect cross-call patterns across the meeting corpus.

Insight types:
  - client_stated_priority: What the CLIENT said matters to THEM — their words,
                            their emphasis, their beliefs. These get mirrored
                            back in every deliverable to show we listened.
  - client_request:         What the client asked for, urgency, context
  - strategic_decision:     What was decided, by whom, rationale
  - action_item:            Task, owner, deadline
  - methodology:            Repeatable frameworks described by practitioners
  - competitive_intel:      Competitor mentions, positioning, market signals
  - cross_client_pattern:   Theme that surfaces across multiple clients/calls
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lib.fireflies.client import FirefliesTranscript
from lib.fireflies.classifier import Classification

logger = logging.getLogger(__name__)


@dataclass
class MeetingInsight:
    """A single structured insight extracted from a meeting."""

    insight_id: str
    meeting_id: str
    insight_type: str
    title: str
    content: str
    speaker: str
    domains: List[str]
    concepts: List[str]  # normalized concept tags for cross-call matching
    confidence: float
    client_id: Optional[str] = None
    timestamp_in_meeting: Optional[float] = None
    mirror_in_deliverables: bool = False  # must be reflected back in decks/assessments
    client_verbatim: str = ""  # their exact words, preserved for mirroring
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "insight_id": self.insight_id,
            "meeting_id": self.meeting_id,
            "insight_type": self.insight_type,
            "title": self.title,
            "content": self.content,
            "speaker": self.speaker,
            "domains": self.domains,
            "concepts": self.concepts,
            "confidence": self.confidence,
            "client_id": self.client_id,
            "timestamp_in_meeting": self.timestamp_in_meeting,
            "mirror_in_deliverables": self.mirror_in_deliverables,
            "created_at": self.created_at,
        }
        if self.client_verbatim:
            d["client_verbatim"] = self.client_verbatim
        return d


@dataclass
class CrossCallConnection:
    """A detected pattern linking insights across multiple calls."""

    connection_id: str
    insight_ids: List[str]
    meeting_ids: List[str]
    pattern_type: str  # "convergent_diagnosis", "shared_methodology", "recurring_theme"
    title: str
    description: str
    domains: List[str]
    shared_concepts: List[str]
    strength: float  # 0-1, how strong the connection is
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "insight_ids": self.insight_ids,
            "meeting_ids": self.meeting_ids,
            "pattern_type": self.pattern_type,
            "title": self.title,
            "description": self.description,
            "domains": self.domains,
            "shared_concepts": self.shared_concepts,
            "strength": self.strength,
            "created_at": self.created_at,
        }


def _generate_insight_id(meeting_id: str, index: int, title: str) -> str:
    raw = f"{meeting_id}:{index}:{title}"
    return f"mi-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _generate_connection_id(insight_ids: List[str]) -> str:
    raw = ":".join(sorted(insight_ids))
    return f"mc-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


# ── Extraction prompt ──────────────────────────────────────────────────

_EXTRACTION_PROMPT = """\
You are an intelligence analyst for a marketing operations company (MH1).
Extract structured insights from the meeting transcript below.

For EACH distinct insight, provide:
- type: one of "client_stated_priority", "client_request", "strategic_decision", "action_item", "methodology", "competitive_intel", "cross_client_pattern"
- title: concise (<80 chars) descriptive title
- content: detailed description including context, rationale, and specifics (200-800 chars)
- speaker: who articulated this (full name)
- domains: relevant business domains (e.g. "attribution", "paid_media", "lifecycle", "crm", "seo", "content", "analytics", "retention", "acquisition")
- concepts: normalized concept tags for pattern matching (e.g. "incrementality_testing", "last_click_attribution", "multi_touch_attribution", "creative_fatigue", "demand_generation")
- confidence: 0.0-1.0 how clearly this was stated
- mirror_in_deliverables: true/false — whether this MUST be reflected back in strategy decks, assessments, and presentations delivered to this client
- client_verbatim: (only for client_stated_priority) the client's exact words or near-exact phrasing, preserved for mirroring back

INSIGHT TYPES — extract ALL that apply:

1. **Client-stated priorities** (MOST IMPORTANT) — things the client/stakeholder said that THEY clearly believe matter. Not what we think is strategic — what THEY emphasized. Listen for: repeated points, emotional conviction, beliefs they hold strongly, pain points they keep returning to, metrics they care about, outcomes they're fixated on. These MUST be mirrored back in every deliverable we produce. Even if they seem obvious or wrong — if the client said it with emphasis, log it. Set mirror_in_deliverables=true and capture their exact words in client_verbatim.

2. **Client requests** — what the client explicitly asked for, urgency level, constraints, deadlines

3. **Strategic decisions** — what was decided, by whom, the rationale, and what alternatives were rejected

4. **Action items** — specific tasks with owners and deadlines when stated

5. **Methodologies** — repeatable frameworks, diagnostic approaches, analytical processes that practitioners describe (high-value for encoding into the system)

6. **Competitive intel** — competitor mentions, market positioning, tool/platform evaluations

7. **Cross-client patterns** — when someone describes a problem or solution that applies across multiple clients or industries

CRITICAL GUIDANCE on client_stated_priority:
- It doesn't matter if what they said is technically correct. If the client expressed it as important, it IS important to capture.
- Look for phrases like "I really think...", "the thing that concerns me most...", "what we need to focus on...", "I keep coming back to...", "that's what keeps me up at night..."
- Also capture beliefs they state with conviction even without hedging — "our creative isn't working", "we're spending too much on Google", "our attribution is broken"
- A single meeting can have 3-8 client_stated_priority insights. Don't under-extract these.
- Any insight from a client/external stakeholder that reveals what they VALUE should also get mirror_in_deliverables=true, even if typed as something else (e.g. a client_request that reveals a core belief).

Be thorough. Extract EVERY substantive insight — a 30-minute call typically yields 10-25 insights.
Do NOT extract small talk, greetings, or logistical scheduling.

Meeting classification: {meeting_type}
{client_context}

--- TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---

Return a JSON array of insights. Examples:
[
  {{
    "type": "client_stated_priority",
    "title": "Attribution is broken and nothing else matters until it's fixed",
    "content": "Jen believes the core problem is broken attribution, not channel performance. She framed it as the root cause that makes all other analysis unreliable. Her conviction was strong — she wants to walk into the exec meeting with proof that fixing measurement is prerequisite to everything else.",
    "speaker": "Jen",
    "domains": ["attribution", "analytics", "measurement"],
    "concepts": ["broken_attribution", "measurement_first", "executive_alignment"],
    "confidence": 0.95,
    "mirror_in_deliverables": true,
    "client_verbatim": "If you don't fix this at the root, the rest of it's pointless."
  }},
  {{
    "type": "methodology",
    "title": "Hypothesis-driven DTC revenue diagnosis",
    "content": "Himanshu described a structured diagnostic framework: (1) Product lens — which categories drive decline using 80/20, (2) Customer lens — new vs returning cohort contribution, which cohorts declining fastest, (3) Channel lens — which marketing channel weakest YoY, (4) Generate 3-5 falsifiable hypotheses from patterns, (5) Find data to disprove each. Survivors become the action plan.",
    "speaker": "Himanshu Sinha",
    "domains": ["analytics", "strategy", "dtc"],
    "concepts": ["hypothesis_driven_analysis", "cohort_analysis", "revenue_diagnosis", "segmentation"],
    "confidence": 0.95,
    "mirror_in_deliverables": false,
    "client_verbatim": ""
  }}
]

Return ONLY the JSON array, no other text."""


def extract_insights(
    transcript: FirefliesTranscript,
    classification: Classification,
) -> List[MeetingInsight]:
    """
    Extract structured insights from a meeting transcript using Claude Haiku.

    Returns a list of MeetingInsight objects with normalized concept tags
    for downstream cross-call matching.
    """
    client_context = ""
    if classification.client_id:
        client_context = f"Client: {classification.client_name} (ID: {classification.client_id})"

    transcript_text = transcript.full_text
    if len(transcript_text) > 100_000:
        transcript_text = transcript_text[:100_000] + "\n\n... (truncated)"

    prompt = _EXTRACTION_PROMPT.format(
        meeting_type=classification.meeting_type,
        client_context=client_context,
        transcript=transcript_text,
    )

    try:
        raw_insights = _call_extraction_llm(prompt)
    except Exception as e:
        logger.error("Insight extraction failed for %s: %s", transcript.id, e)
        return []

    insights: List[MeetingInsight] = []
    for i, raw in enumerate(raw_insights):
        insight_type = raw.get("type", "strategic_decision")
        mirror = bool(raw.get("mirror_in_deliverables", False))
        # client_stated_priority always mirrors
        if insight_type == "client_stated_priority":
            mirror = True

        insight = MeetingInsight(
            insight_id=_generate_insight_id(transcript.id, i, raw.get("title", "")),
            meeting_id=transcript.id,
            insight_type=insight_type,
            title=raw.get("title", ""),
            content=raw.get("content", ""),
            speaker=raw.get("speaker", ""),
            domains=raw.get("domains", []),
            concepts=[c.lower().replace(" ", "_") for c in raw.get("concepts", [])],
            confidence=float(raw.get("confidence", 0.5)),
            client_id=classification.client_id,
            mirror_in_deliverables=mirror,
            client_verbatim=raw.get("client_verbatim", ""),
        )
        insights.append(insight)

    priority_count = sum(
        1 for i in insights if i.insight_type == "client_stated_priority"
    )
    mirror_count = sum(1 for i in insights if i.mirror_in_deliverables)
    logger.info(
        "Extracted %d insights from meeting %s (%s) — "
        "%d client priorities, %d flagged for deliverable mirroring",
        len(insights), transcript.id, transcript.title,
        priority_count, mirror_count,
    )
    return insights


def _call_extraction_llm(prompt: str) -> List[Dict[str, Any]]:
    """Call Claude Haiku for insight extraction. Returns parsed JSON list."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package required for insight extraction")

    import os
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )

    response = client.messages.create(
        model="claude-haiku-4-20250414",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()

    # Parse JSON — handle potential markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError:
        logger.warning("Failed to parse extraction result as JSON")
        return []


# ── Cross-call connection detection ─────────────────────────────────────


def detect_connections(
    new_insights: List[MeetingInsight],
    existing_insights: List[Dict[str, Any]],
    min_concept_overlap: int = 2,
    min_strength: float = 0.4,
) -> List[CrossCallConnection]:
    """
    Detect cross-call patterns by comparing concept overlap between
    new insights and the existing corpus.

    A connection is created when:
      1. Two insights from DIFFERENT meetings share >= min_concept_overlap concepts
      2. The computed strength (Jaccard similarity on concepts) >= min_strength
      3. The insights are from different speakers or different clients (not self-links)

    Connection types:
      - convergent_diagnosis: Different people independently identify the same problem
      - shared_methodology:   Same analytical framework described in multiple contexts
      - recurring_theme:      Same topic/concept surfaces across calls
    """
    connections: List[CrossCallConnection] = []
    seen_pairs: set[tuple[str, str]] = set()

    for new_insight in new_insights:
        new_concepts = set(new_insight.concepts)
        if len(new_concepts) < 2:
            continue

        for existing in existing_insights:
            existing_meeting = existing.get("meeting_id", "")
            if existing_meeting == new_insight.meeting_id:
                continue

            existing_id = existing.get("insight_id", "")
            pair_key = tuple(sorted([new_insight.insight_id, existing_id]))
            if pair_key in seen_pairs:
                continue

            existing_concepts = set(existing.get("concepts", []))
            overlap = new_concepts & existing_concepts

            if len(overlap) < min_concept_overlap:
                continue

            union = new_concepts | existing_concepts
            strength = len(overlap) / len(union) if union else 0
            if strength < min_strength:
                continue

            seen_pairs.add(pair_key)

            pattern_type = _infer_pattern_type(new_insight, existing, overlap)
            all_domains = list(
                set(new_insight.domains) | set(existing.get("domains", []))
            )

            connection = CrossCallConnection(
                connection_id=_generate_connection_id(
                    [new_insight.insight_id, existing_id]
                ),
                insight_ids=[new_insight.insight_id, existing_id],
                meeting_ids=[new_insight.meeting_id, existing_meeting],
                pattern_type=pattern_type,
                title=f"Cross-call: {', '.join(sorted(overlap)[:3])}",
                description=(
                    f"'{new_insight.title}' (from meeting {new_insight.meeting_id}) "
                    f"connects to '{existing.get('title', '')}' "
                    f"(from meeting {existing_meeting}) "
                    f"via shared concepts: {', '.join(sorted(overlap))}"
                ),
                domains=all_domains,
                shared_concepts=sorted(overlap),
                strength=round(strength, 3),
            )
            connections.append(connection)

    if connections:
        logger.info(
            "Detected %d cross-call connections for %d new insights",
            len(connections), len(new_insights),
        )

    return connections


def _infer_pattern_type(
    insight_a: MeetingInsight,
    insight_b: Dict[str, Any],
    overlap: set[str],
) -> str:
    """Infer the type of cross-call connection from the insights."""
    a_type = insight_a.insight_type
    b_type = insight_b.get("insight_type", "")

    diagnosis_types = {"client_request", "competitive_intel", "cross_client_pattern"}
    if a_type in diagnosis_types or b_type in diagnosis_types:
        if insight_a.speaker != insight_b.get("speaker", ""):
            return "convergent_diagnosis"

    if a_type == "methodology" or b_type == "methodology":
        return "shared_methodology"

    return "recurring_theme"
