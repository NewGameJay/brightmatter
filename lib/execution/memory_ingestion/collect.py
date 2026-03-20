"""
Artifact collection for memory ingestion.

Scans a run directory and loads all persisted artifacts that can be
ingested into memory. Phase-leader-aware: supports "best" and "final"
attempt selection strategies.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import MemoryIngestionConfig

logger = logging.getLogger(__name__)


def _load_json_safe(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None on missing or corrupt files."""
    try:
        if not path.exists():
            return None
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, PermissionError):
        return None


# ── Per-artifact shape validation ──────────────────────────────────────

# Required keys per artifact type. If any required key is missing,
# the artifact is skipped and counted as shape-invalid.
_ARTIFACT_SHAPE_REQUIREMENTS: Dict[str, Dict[str, type]] = {
    "phase_leader_summary": {"leader_ran": None, "phase_id": None},
    "phase_leader_summary_legacy": {"decision": None},
    "policy_usage": {"total_calls": None},
    "policy_usage_legacy": {"total_tool_calls": None},
    "policy_violations": {"violations": list},
    "evidence_ledger": {"entries": list},
    "validation": {"status": None, "checks": list},
    "phase_digest": {"entries": list},
}


def _check_artifact_shape(
    artifact_type: str, data: Dict[str, Any], source_hint: str,
) -> bool:
    """
    Check required keys for an artifact type. Returns True if valid.

    Accepts both current and legacy field names for drift tolerance.
    """
    # Try primary shape first, then legacy if defined
    primary_key = artifact_type
    legacy_key = f"{artifact_type}_legacy"

    for shape_key in (primary_key, legacy_key):
        reqs = _ARTIFACT_SHAPE_REQUIREMENTS.get(shape_key)
        if reqs is None:
            continue
        all_present = True
        for key, expected_type in reqs.items():
            if key not in data:
                all_present = False
                break
            if expected_type is not None and not isinstance(data[key], expected_type):
                all_present = False
                break
        if all_present:
            return True

    # If we only have primary (no legacy), check that primary's keys exist
    primary_reqs = _ARTIFACT_SHAPE_REQUIREMENTS.get(primary_key, {})
    missing = [k for k in primary_reqs if k not in data]
    if missing:
        logger.warning(
            "Shape check failed for %s at %s: missing keys %s",
            artifact_type, source_hint, missing,
        )
        return False
    return True


@dataclass
class CollectionStats:
    """Statistics about what was found during collection."""
    nodes_scanned: int = 0
    nodes_included: int = 0
    nodes_skipped_failed: int = 0
    phase_digests_found: int = 0
    findings_packs_found: int = 0
    validations_found: int = 0
    evidence_ledgers_found: int = 0
    policy_artifacts_found: int = 0
    phase_leader_summaries_found: int = 0
    artifacts_shape_invalid: int = 0
    attempts_selected_by_best: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "nodes_scanned": self.nodes_scanned,
            "nodes_included": self.nodes_included,
            "nodes_skipped_failed": self.nodes_skipped_failed,
            "phase_digests_found": self.phase_digests_found,
            "findings_packs_found": self.findings_packs_found,
            "validations_found": self.validations_found,
            "evidence_ledgers_found": self.evidence_ledgers_found,
            "policy_artifacts_found": self.policy_artifacts_found,
            "phase_leader_summaries_found": self.phase_leader_summaries_found,
            "artifacts_shape_invalid": self.artifacts_shape_invalid,
            "attempts_selected_by_best": self.attempts_selected_by_best,
        }


@dataclass
class CollectedArtifacts:
    """All discoverable artifacts from a run directory."""
    run_id: str
    module_id: str
    client_id: str
    run_dir: Path
    state: Dict[str, Any]
    plan: Dict[str, Any]
    node_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    node_errors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    node_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    phase_digests: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    findings_packs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    validations: Dict[str, Tuple[Dict[str, Any], str]] = field(default_factory=dict)
    evidence_ledgers: Dict[str, Tuple[Dict[str, Any], str]] = field(default_factory=dict)
    policy_usage: Dict[str, Tuple[Dict[str, Any], str]] = field(default_factory=dict)
    policy_violations: Dict[str, Tuple[Dict[str, Any], str]] = field(default_factory=dict)
    phase_leader_summaries: Dict[str, Tuple[Dict[str, Any], str]] = field(default_factory=dict)
    telemetry_summary: Optional[Dict[str, Any]] = None
    selected_attempts: Dict[str, int] = field(default_factory=dict)
    stats: CollectionStats = field(default_factory=CollectionStats)


def _get_final_attempt(node_state: Dict[str, Any]) -> int:
    """Get the final attempt number for a node from its state."""
    return max(int(node_state.get("attempt", 1)), 1)


def _find_best_attempt(run_dir: Path, node_id: str, max_attempt: int) -> Optional[int]:
    """
    Scan attempts/1..max_attempt/validation.json and return the attempt
    number with the highest score. Returns None if no validation.json exists.
    """
    best_attempt = None
    best_score = -1.0
    for attempt_num in range(1, max_attempt + 1):
        val_path = run_dir / "nodes" / node_id / "attempts" / str(attempt_num) / "validation.json"
        data = _load_json_safe(val_path)
        if data is None:
            continue
        score = data.get("score")
        if score is not None:
            try:
                score_float = float(score)
            except (ValueError, TypeError):
                continue
            if score_float > best_score:
                best_score = score_float
                best_attempt = attempt_num
    return best_attempt


def _find_validation(run_dir: Path, node_id: str, selected_attempt: int) -> Optional[Tuple[Dict[str, Any], str]]:
    """Find the validation artifact for the selected attempt of a node."""
    attempt_path = run_dir / "nodes" / node_id / "attempts" / str(selected_attempt) / "validation.json"
    if attempt_path.exists():
        data = _load_json_safe(attempt_path)
        if data:
            return (data, str(attempt_path.relative_to(run_dir)))
    node_path = run_dir / "nodes" / node_id / "validation.json"
    data = _load_json_safe(node_path)
    if data:
        return (data, str(node_path.relative_to(run_dir)))
    return None


def _find_evidence_ledger(run_dir: Path, node_id: str, selected_attempt: int) -> Optional[Tuple[Dict[str, Any], str]]:
    """Find the evidence ledger for the selected attempt of a node."""
    # Primary path: attempts/<n>/evidence/evidence_ledger.json (actual producer path)
    for name in ("evidence/evidence_ledger.json", "evidence.json"):
        attempt_path = run_dir / "nodes" / node_id / "attempts" / str(selected_attempt) / name
        if attempt_path.exists():
            data = _load_json_safe(attempt_path)
            if data:
                return (data, str(attempt_path.relative_to(run_dir)))
    # Fallback: node-level paths
    for name in ("evidence/evidence_ledger.json", "evidence.json"):
        node_path = run_dir / "nodes" / node_id / name
        data = _load_json_safe(node_path)
        if data:
            return (data, str(node_path.relative_to(run_dir)))
    return None


def _find_policy_artifacts(
    run_dir: Path, node_id: str, selected_attempt: int,
) -> Tuple[Optional[Tuple[Dict[str, Any], str]], Optional[Tuple[Dict[str, Any], str]]]:
    """Find policy usage and violation artifacts for a node (attempt-scoped first)."""
    usage = None
    violations = None

    # Try attempt-scoped paths first (actual producer path)
    for attempt_num in (selected_attempt,):
        usage_path = run_dir / "nodes" / node_id / "attempts" / str(attempt_num) / "policy" / "policy_usage.json"
        data = _load_json_safe(usage_path)
        if data:
            usage = (data, str(usage_path.relative_to(run_dir)))
        violations_path = run_dir / "nodes" / node_id / "attempts" / str(attempt_num) / "policy" / "policy_violations.json"
        data = _load_json_safe(violations_path)
        if data:
            violations = (data, str(violations_path.relative_to(run_dir)))

    # Fallback to node-level paths (legacy)
    if usage is None:
        usage_path = run_dir / "nodes" / node_id / "policy" / "policy_usage.json"
        data = _load_json_safe(usage_path)
        if data:
            usage = (data, str(usage_path.relative_to(run_dir)))
    if violations is None:
        violations_path = run_dir / "nodes" / node_id / "policy" / "policy_violations.json"
        data = _load_json_safe(violations_path)
        if data:
            violations = (data, str(violations_path.relative_to(run_dir)))

    return usage, violations


def collect_artifacts(
    run_dir: Path,
    config: MemoryIngestionConfig,
) -> Optional[CollectedArtifacts]:
    """
    Scan the run directory and load all persisted artifacts.

    Attempt strategy:
        "best"  — Select the attempt with the highest validation score.
                   Falls back to "final" if no validation data exists.
        "final" — Select the last attempt (what Phase Leader settled on).

    Validation-aware: skips failed nodes if config.include_failed is False.

    Returns None if state.json is missing or unreadable.
    """
    run_dir = Path(run_dir)
    state = _load_json_safe(run_dir / "state.json")
    if state is None:
        return None

    plan = _load_json_safe(run_dir / "plan.json") or {}

    result = CollectedArtifacts(
        run_id=state.get("run_id", ""),
        module_id=state.get("module_id", ""),
        client_id=state.get("client_id", ""),
        run_dir=run_dir,
        state=state,
        plan=plan,
    )
    stats = result.stats
    nodes_data = state.get("nodes", {})

    for node_id, node_state in sorted(nodes_data.items()):
        stats.nodes_scanned += 1
        node_status = node_state.get("state", "unknown")
        if node_status == "failed" and not config.include_failed:
            stats.nodes_skipped_failed += 1
            continue

        stats.nodes_included += 1
        result.node_states[node_id] = node_state
        final_attempt = _get_final_attempt(node_state)

        # Attempt selection
        selected_attempt = final_attempt
        if config.attempt_strategy == "best" and final_attempt > 1:
            best = _find_best_attempt(run_dir, node_id, final_attempt)
            if best is not None and best != final_attempt:
                selected_attempt = best
                stats.attempts_selected_by_best += 1
        result.selected_attempts[node_id] = selected_attempt

        node_result = _load_json_safe(run_dir / "nodes" / node_id / "result.json")
        if node_result:
            result.node_results[node_id] = node_result
        node_error = _load_json_safe(run_dir / "nodes" / node_id / "error.json")
        if node_error:
            result.node_errors[node_id] = node_error

        # Validation (shape check: status + checks required)
        validation = _find_validation(run_dir, node_id, selected_attempt)
        if validation:
            vdata, vpath = validation
            if _check_artifact_shape("validation", vdata, vpath):
                result.validations[node_id] = validation
                stats.validations_found += 1
            else:
                stats.artifacts_shape_invalid += 1

        # Evidence ledger (shape check: entries list required)
        evidence = _find_evidence_ledger(run_dir, node_id, selected_attempt)
        if evidence:
            edata, epath = evidence
            if _check_artifact_shape("evidence_ledger", edata, epath):
                result.evidence_ledgers[node_id] = evidence
                stats.evidence_ledgers_found += 1
            else:
                stats.artifacts_shape_invalid += 1

        # Policy artifacts (shape checks inline)
        usage, violations = _find_policy_artifacts(run_dir, node_id, selected_attempt)
        if usage:
            udata, upath = usage
            if _check_artifact_shape("policy_usage", udata, upath):
                result.policy_usage[node_id] = usage
                stats.policy_artifacts_found += 1
            else:
                stats.artifacts_shape_invalid += 1
        if violations:
            vdata, vpath = violations
            if _check_artifact_shape("policy_violations", vdata, vpath):
                result.policy_violations[node_id] = violations
            else:
                stats.artifacts_shape_invalid += 1

    phases_dir = run_dir / "phases"
    if phases_dir.is_dir():
        for phase_subdir in sorted(phases_dir.iterdir()):
            if not phase_subdir.is_dir():
                continue
            phase_id = phase_subdir.name

            # Phase digest (shape check: entries list required)
            digest_path = phase_subdir / "digest" / "phase_digest.json"
            digest = _load_json_safe(digest_path)
            if digest:
                if _check_artifact_shape("phase_digest", digest, str(digest_path)):
                    result.phase_digests[phase_id] = digest
                    stats.phase_digests_found += 1
                else:
                    stats.artifacts_shape_invalid += 1

            # Findings pack (Package I1) — no shape check needed, schema-validated on write
            fp_path = phase_subdir / "findings_pack" / "findings_pack.json"
            fp = _load_json_safe(fp_path)
            if fp:
                result.findings_packs[phase_id] = fp
                stats.findings_packs_found += 1

            # Phase leader summary (shape check: leader_ran or legacy decision)
            leader_path = phase_subdir / "phase_leader" / "phase_leader_summary.json"
            leader = _load_json_safe(leader_path)
            if leader:
                rel = str(leader_path.relative_to(run_dir))
                if _check_artifact_shape("phase_leader_summary", leader, rel):
                    result.phase_leader_summaries[phase_id] = (leader, rel)
                    stats.phase_leader_summaries_found += 1
                else:
                    stats.artifacts_shape_invalid += 1

    result.telemetry_summary = _load_json_safe(run_dir / "telemetry" / "summary.json")
    return result
