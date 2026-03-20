"""
Bundle assembly and capping for memory ingestion.

Assembles all transformed entries into a bounded IngestionBundle,
enforces hard caps, and writes artifacts to the run directory.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import MemoryIngestionConfig
from .collect import CollectedArtifacts
from .transform import (
    IngestionEntry,
    _get_phase_node_ids,
    transform_run_summary,
    transform_skill_outcome,
    transform_digest_entries,
    transform_findings_pack_findings,
    transform_validation,
    transform_evidence_ledger,
    transform_phase_leader,
    transform_policy_usage,
    transform_policy_violations,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_node_to_phase(plan: Dict[str, Any]) -> Dict[str, str]:
    """Build a node_id -> phase_id lookup from plan phases."""
    mapping: Dict[str, str] = {}
    for phase in plan.get("phases", []):
        phase_id = phase.get("phase_id", "")
        if not phase_id:
            continue
        for nid in _get_phase_node_ids(phase):
            mapping[nid] = phase_id
    return mapping


def _validate_against_schema(data: Dict[str, Any], schema_name: str) -> Optional[str]:
    """
    Validate data against a JSON schema. Returns error message or None.
    Non-blocking: never raises.
    """
    try:
        import jsonschema
        schema_path = Path(__file__).resolve().parents[3] / "schemas" / schema_name
        if not schema_path.exists():
            return f"Schema file not found: {schema_name}"
        schema = json.loads(schema_path.read_text())
        jsonschema.validate(instance=data, schema=schema)
        return None
    except ImportError:
        logger.debug("jsonschema not installed, skipping schema validation")
        return None
    except Exception as e:
        return str(e)


def assemble_bundle(
    artifacts: CollectedArtifacts,
    config: MemoryIngestionConfig,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Transform all collected artifacts into a bounded ingestion bundle.
    Returns (bundle_dict, report_dict).
    """
    run_id = artifacts.run_id
    plan = artifacts.plan
    all_entries: List[IngestionEntry] = []
    errors: List[str] = []

    # Build node-to-phase lookup for phase_id resolution
    node_to_phase = _build_node_to_phase(plan)

    # 1. Run summary
    try:
        all_entries.extend(transform_run_summary(run_id, artifacts.state, plan, artifacts.telemetry_summary))
    except Exception as e:
        errors.append(f"run_summary: {e}")

    # 2. Skill outcomes (with attempt metadata)
    for node_id, node_state in sorted(artifacts.node_states.items()):
        try:
            selected = artifacts.selected_attempts.get(node_id)
            final = node_state.get("attempt", 1)
            all_entries.extend(transform_skill_outcome(
                run_id, node_id, node_state,
                artifacts.node_results.get(node_id), plan,
                selected_attempt=selected,
                final_attempt=final,
            ))
        except Exception as e:
            errors.append(f"skill_outcome {node_id}: {e}")

    # 3. Digest findings
    for phase_id, digest in sorted(artifacts.phase_digests.items()):
        try:
            all_entries.extend(transform_digest_entries(run_id, phase_id, digest))
        except Exception as e:
            errors.append(f"digest {phase_id}: {e}")

    # 3b. Findings pack findings (Package I1)
    for phase_id, pack in sorted(artifacts.findings_packs.items()):
        try:
            all_entries.extend(transform_findings_pack_findings(run_id, phase_id, pack))
        except Exception as e:
            errors.append(f"findings_pack {phase_id}: {e}")

    # 4. Validation results
    for node_id, (validation, source_path) in sorted(artifacts.validations.items()):
        try:
            all_entries.extend(transform_validation(run_id, node_id, validation, source_path, plan))
        except Exception as e:
            errors.append(f"validation {node_id}: {e}")

    # 5. Evidence summaries
    for node_id, (ledger, source_path) in sorted(artifacts.evidence_ledgers.items()):
        try:
            all_entries.extend(transform_evidence_ledger(run_id, node_id, ledger, source_path, plan))
        except Exception as e:
            errors.append(f"evidence {node_id}: {e}")

    # 6. Phase leader decisions
    for phase_id, (summary, source_path) in sorted(artifacts.phase_leader_summaries.items()):
        try:
            all_entries.extend(transform_phase_leader(run_id, phase_id, summary, source_path))
        except Exception as e:
            errors.append(f"phase_leader {phase_id}: {e}")

    # 7. Tool usage patterns
    for node_id, (usage, source_path) in sorted(artifacts.policy_usage.items()):
        try:
            all_entries.extend(transform_policy_usage(run_id, node_id, usage, source_path, plan))
        except Exception as e:
            errors.append(f"policy_usage {node_id}: {e}")

    # 8. Policy violations
    for node_id, (violations, source_path) in sorted(artifacts.policy_violations.items()):
        try:
            all_entries.extend(transform_policy_violations(run_id, node_id, violations, source_path, plan))
        except Exception as e:
            errors.append(f"policy_violation {node_id}: {e}")

    # Fill in missing phase_id using node_to_phase lookup
    for entry in all_entries:
        if entry.phase_id is None and entry.node_id and entry.node_id in node_to_phase:
            entry.phase_id = node_to_phase[entry.node_id]

    entries_by_type_before = Counter(e.entry_type for e in all_entries)
    total_before = len(all_entries)

    capped_entries, entries_capped, bytes_capped, bytes_before, bytes_after = _apply_caps(all_entries, config)

    skipped_entries = []
    if entries_capped:
        skipped_entries.append({"reason": "max_entries_per_run exceeded", "count": total_before - len(capped_entries)})
    if bytes_capped:
        skipped_entries.append({"reason": "max_bytes_per_bundle exceeded", "count": total_before - len(capped_entries)})
    if artifacts.stats.nodes_skipped_failed > 0:
        skipped_entries.append({"reason": "node_failed (include_failed=false)",
                                "count": artifacts.stats.nodes_skipped_failed})

    bundle = {
        "version": "1",
        "run_id": run_id,
        "module_id": artifacts.module_id,
        "client_id": artifacts.client_id,
        "created_at": _now_iso(),
        "config_mode": config.mode,
        "entry_count": len(capped_entries),
        "entries_capped": entries_capped,
        "bytes_capped": bytes_capped,
        "entries": [e.to_dict() for e in capped_entries],
    }

    report = {
        "version": "1",
        "run_id": run_id,
        "module_id": artifacts.module_id,
        "client_id": artifacts.client_id,
        "created_at": _now_iso(),
        "config": config.to_dict(),
        "collection_stats": artifacts.stats.to_dict(),
        "transform_stats": {
            "total_entries_generated": total_before,
            "entries_by_type": dict(entries_by_type_before),
        },
        "cap_stats": {
            "entries_before_cap": total_before,
            "entries_after_cap": len(capped_entries),
            "bytes_before_cap": bytes_before,
            "bytes_after_cap": bytes_after,
            "entries_dropped": total_before - len(capped_entries),
        },
        "memory_write_stats": None,
        "skipped_entries": skipped_entries,
        "errors": errors,
    }

    return bundle, report


def _apply_caps(
    entries: List[IngestionEntry], config: MemoryIngestionConfig,
) -> Tuple[List[IngestionEntry], bool, bool, int, int]:
    """Apply max_entries_per_run and max_bytes_per_bundle caps."""
    entries_capped = False
    bytes_capped = False
    serialized = json.dumps([e.to_dict() for e in entries], default=str)
    bytes_before = len(serialized.encode("utf-8"))

    if len(entries) > config.max_entries_per_run:
        entries = entries[:config.max_entries_per_run]
        entries_capped = True

    while entries:
        serialized = json.dumps([e.to_dict() for e in entries], default=str)
        current_bytes = len(serialized.encode("utf-8"))
        if current_bytes <= config.max_bytes_per_bundle:
            return entries, entries_capped, bytes_capped, bytes_before, current_bytes
        entries = entries[:-1]
        bytes_capped = True

    return entries, entries_capped, bytes_capped, bytes_before, 2


def write_bundle(bundle: Dict[str, Any], run_dir: Path) -> Path:
    """Write bundle to run_dir/memory/ingestion_bundle.json.

    Validates against schema (warn-only, non-blocking).
    """
    memory_dir = Path(run_dir) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / "ingestion_bundle.json"

    # Runtime schema validation (warn and continue)
    error = _validate_against_schema(bundle, "ingestion_bundle.schema.json")
    if error:
        logger.warning("Bundle schema validation failed (writing anyway): %s", error)

    with open(path, "w") as f:
        json.dump(bundle, f, indent=2, default=str)
    return path


def write_report(report: Dict[str, Any], run_dir: Path) -> Path:
    """Write report to run_dir/memory/ingestion_report.json.

    Validates against schema (warn-only, non-blocking).
    """
    memory_dir = Path(run_dir) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / "ingestion_report.json"

    # Runtime schema validation (warn and continue)
    error = _validate_against_schema(report, "ingestion_report.schema.json")
    if error:
        logger.warning("Report schema validation failed (writing anyway): %s", error)

    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return path
