"""
MH1 Delivery Metadata Extractor

Extracts measurable identifiers from skill execution outputs so the
deferred outcome system knows *what to measure* when checkpoints fire.

Skill-type-aware: lifecycle-audit outputs differ from email-copy-generator
outputs. The extractor knows which keys to look for based on skill domain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeliveryMetadata:
    """Identifiers extracted from skill outputs for deferred measurement."""
    skill_name: str = ""
    delivery_type: str = ""  # report | email_sequence | campaign | strategy | content
    report_url: Optional[str] = None
    campaign_ids: List[str] = field(default_factory=list)
    email_sequence_ids: List[str] = field(default_factory=list)
    workflow_ids: List[str] = field(default_factory=list)
    segment_ids: List[str] = field(default_factory=list)
    list_ids: List[str] = field(default_factory=list)
    file_names: List[str] = field(default_factory=list)
    measurable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "delivery_type": self.delivery_type,
            "report_url": self.report_url,
            "campaign_ids": self.campaign_ids,
            "email_sequence_ids": self.email_sequence_ids,
            "workflow_ids": self.workflow_ids,
            "segment_ids": self.segment_ids,
            "list_ids": self.list_ids,
            "file_names": self.file_names,
            "measurable": self.measurable,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> DeliveryMetadata:
        return cls(
            skill_name=d.get("skill_name", ""),
            delivery_type=d.get("delivery_type", ""),
            report_url=d.get("report_url"),
            campaign_ids=d.get("campaign_ids", []),
            email_sequence_ids=d.get("email_sequence_ids", []),
            workflow_ids=d.get("workflow_ids", []),
            segment_ids=d.get("segment_ids", []),
            list_ids=d.get("list_ids", []),
            file_names=d.get("file_names", []),
            measurable=d.get("measurable", False),
        )


# Skills whose outputs are measurable against platform data
_MEASURABLE_SKILLS: Dict[str, str] = {
    "lifecycle-audit": "strategy",
    "churn-prediction": "strategy",
    "at-risk-detection": "strategy",
    "dormant-detection": "strategy",
    "reactivation-detection": "strategy",
    "pipeline-analysis": "strategy",
    "deal-velocity": "strategy",
    "conversion-funnel": "strategy",
    "upsell-candidates": "strategy",
    "renewal-tracker": "strategy",
    "email-copy-generator": "email_sequence",
    "cohort-email-builder": "email_sequence",
    "lifecycle-communications-sequences": "email_sequence",
    "ghostwrite-content": "content",
    "direct-response-copy": "content",
    "seo-content": "content",
    "positioning-angles": "strategy",
    "creative-brief": "content",
    "experiment-roadmap": "strategy",
    "cold-email-personalization": "email_sequence",
    "social-listening-collect": "campaign",
    "linkedin-keyword-search": "campaign",
    "twitter-keyword-search": "campaign",
    "reddit-keyword-search": "campaign",
}

_ID_KEYS = [
    "campaign_id", "campaign_ids",
    "sequence_id", "sequence_ids", "email_sequence_id",
    "workflow_id", "workflow_ids",
    "segment_id", "segment_ids",
    "list_id", "list_ids",
    "report_url", "deploy_url", "preview_url",
]


class DeliveryExtractor:
    """
    Extracts delivery metadata from skill execution outputs.

    Parses result.json outputs for identifiers (campaign IDs, email
    sequence names, report URLs, etc.) that the deferred checkpoint
    system can use to measure real-world outcomes later.
    """

    @staticmethod
    def extract(
        skill_name: str,
        outputs: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> DeliveryMetadata:
        """
        Extract delivery metadata from a completed skill's outputs.

        Args:
            skill_name: Name of the skill that produced the outputs.
            outputs: The skill's output dict (from result.json).
            metrics: Optional execution metrics dict.
        """
        delivery_type = _MEASURABLE_SKILLS.get(skill_name, "")
        meta = DeliveryMetadata(
            skill_name=skill_name,
            delivery_type=delivery_type,
            measurable=bool(delivery_type),
        )

        if not delivery_type:
            return meta

        files = outputs.get("files", {})
        if isinstance(files, dict):
            meta.file_names = list(files.keys())
            for fname, content in files.items():
                _extract_ids_from_content(content, meta)

        for key in ["output", "result", "deliverables"]:
            val = outputs.get(key)
            if isinstance(val, dict):
                _extract_ids_from_content(val, meta)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        _extract_ids_from_content(item, meta)

        if metrics:
            _extract_ids_from_content(metrics, meta)

        if meta.report_url or meta.campaign_ids or meta.email_sequence_ids:
            meta.measurable = True

        return meta


def _extract_ids_from_content(content: Any, meta: DeliveryMetadata) -> None:
    """Recursively scan content for identifiable delivery artifacts."""
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                _extract_ids_from_content(parsed, meta)
                return
        except (json.JSONDecodeError, TypeError):
            pass
        return

    if not isinstance(content, dict):
        return

    for key, val in content.items():
        key_lower = key.lower()

        if key_lower in ("campaign_id",) and isinstance(val, str) and val:
            meta.campaign_ids.append(val)
        elif key_lower in ("campaign_ids",) and isinstance(val, list):
            meta.campaign_ids.extend(v for v in val if isinstance(v, str))

        elif key_lower in ("sequence_id", "email_sequence_id") and isinstance(val, str) and val:
            meta.email_sequence_ids.append(val)
        elif key_lower in ("sequence_ids",) and isinstance(val, list):
            meta.email_sequence_ids.extend(v for v in val if isinstance(v, str))

        elif key_lower in ("workflow_id",) and isinstance(val, str) and val:
            meta.workflow_ids.append(val)
        elif key_lower in ("workflow_ids",) and isinstance(val, list):
            meta.workflow_ids.extend(v for v in val if isinstance(v, str))

        elif key_lower in ("segment_id",) and isinstance(val, str) and val:
            meta.segment_ids.append(val)
        elif key_lower in ("segment_ids",) and isinstance(val, list):
            meta.segment_ids.extend(v for v in val if isinstance(v, str))

        elif key_lower in ("list_id",) and isinstance(val, str) and val:
            meta.list_ids.append(val)
        elif key_lower in ("list_ids",) and isinstance(val, list):
            meta.list_ids.extend(v for v in val if isinstance(v, str))

        elif key_lower in ("report_url", "deploy_url", "preview_url") and isinstance(val, str) and val:
            meta.report_url = meta.report_url or val

        elif isinstance(val, dict):
            _extract_ids_from_content(val, meta)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    _extract_ids_from_content(item, meta)


__all__ = ["DeliveryExtractor", "DeliveryMetadata"]
