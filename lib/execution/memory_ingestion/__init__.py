"""
Memory Ingestion (Package I2)

Automatic extraction and ingestion of structured learnings from completed
execution runs into the MH1 intelligence memory system.

This module is additive and disabled by default via feature flags.
All ingested entries carry full provenance (source paths, timestamps,
deterministic IDs) and are bounded by hard caps.

Feature flags (in plan.json features):
    "memory_ingestion": {
        "enabled": false,
        "mode": "off",           // "off" | "warn" | "enforce"
        "include_failed": false,
        "max_entries_per_run": 200,
        "max_bytes_per_bundle": 524288
    }

Modes:
    off     — No action (default)
    warn    — Write artifacts to disk only (no memory store writes)
    enforce — Write artifacts AND push to memory stores
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Hard caps (non-negotiable bounds) ─────────────────────────────────

MAX_ENTRIES_PER_RUN = 200
MAX_BYTES_PER_BUNDLE = 524_288  # 512 KB
MAX_ENTRIES_PER_PHASE = 50
MAX_DATA_CHARS_PER_ENTRY = 2_000

VALID_MODES = frozenset({"off", "warn", "enforce"})
VALID_ATTEMPT_STRATEGIES = frozenset({"final", "best"})

ENTRY_TYPES = frozenset({
    "run_summary",
    "skill_outcome",
    "digest_finding",
    "findings_pack_finding",
    "validation_result",
    "evidence_summary",
    "phase_leader_decision",
    "tool_usage_pattern",
    "policy_violation",
})

# Priority order for capping: higher priority entries are kept first
ENTRY_TYPE_PRIORITY = [
    "run_summary",
    "skill_outcome",
    "digest_finding",
    "findings_pack_finding",
    "validation_result",
    "evidence_summary",
    "phase_leader_decision",
    "tool_usage_pattern",
    "policy_violation",
]


# ── Configuration ─────────────────────────────────────────────────────

@dataclass
class MemoryIngestionConfig:
    """
    Configuration for memory ingestion, loaded from plan features.

    Example plan.json features block:
        "features": {
            "memory_ingestion": {
                "enabled": true,
                "mode": "warn",
                "include_failed": false,
                "max_entries_per_run": 200,
                "max_bytes_per_bundle": 524288
            }
        }
    """

    enabled: bool = True
    mode: str = "warn"  # "off" | "warn" | "enforce"
    include_failed: bool = False
    max_entries_per_run: int = MAX_ENTRIES_PER_RUN
    max_bytes_per_bundle: int = MAX_BYTES_PER_BUNDLE
    attempt_strategy: str = "best"  # "final" | "best"

    @classmethod
    def from_features(cls, features: Optional[Dict[str, Any]]) -> "MemoryIngestionConfig":
        """Load config from plan features dict. Returns disabled config if absent."""
        if not features:
            return cls()
        mi_cfg = features.get("memory_ingestion", {})
        if not isinstance(mi_cfg, dict):
            return cls()
        mode = str(mi_cfg.get("mode", "off"))
        if mode not in VALID_MODES:
            mode = "off"
        attempt_strategy = str(mi_cfg.get("attempt_strategy", "best"))
        if attempt_strategy not in VALID_ATTEMPT_STRATEGIES:
            attempt_strategy = "best"
        return cls(
            enabled=bool(mi_cfg.get("enabled", False)),
            mode=mode,
            include_failed=bool(mi_cfg.get("include_failed", False)),
            max_entries_per_run=min(
                int(mi_cfg.get("max_entries_per_run", MAX_ENTRIES_PER_RUN)),
                MAX_ENTRIES_PER_RUN,
            ),
            max_bytes_per_bundle=min(
                int(mi_cfg.get("max_bytes_per_bundle", MAX_BYTES_PER_BUNDLE)),
                MAX_BYTES_PER_BUNDLE,
            ),
            attempt_strategy=attempt_strategy,
        )

    @property
    def is_active(self) -> bool:
        """Check if ingestion should run (enabled AND mode is not off)."""
        return self.enabled and self.mode != "off"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config for inclusion in reports."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "include_failed": self.include_failed,
            "max_entries_per_run": self.max_entries_per_run,
            "max_bytes_per_bundle": self.max_bytes_per_bundle,
            "attempt_strategy": self.attempt_strategy,
        }
