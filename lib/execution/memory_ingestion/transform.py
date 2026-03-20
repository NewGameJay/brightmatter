"""
Artifact-to-entry transformation for memory ingestion.

Pure functions that convert collected run artifacts into structured
IngestionEntry objects with deterministic IDs and full provenance.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import MAX_DATA_CHARS_PER_ENTRY


@dataclass
class IngestionEntry:
    """A single memory ingestion entry with full provenance."""
    entry_id: str
    entry_type: str
    source_path: str
    node_id: Optional[str] = None
    phase_id: Optional[str] = None
    skill_id: Optional[str] = None
    timestamp: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "source_path": self.source_path,
            "node_id": self.node_id,
            "phase_id": self.phase_id,
            "skill_id": self.skill_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "confidence": self.confidence,
        }


def generate_entry_id(
    run_id: str,
    entry_type: str,
    node_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    discriminator: str = "",
) -> str:
    """Generate a deterministic entry ID. Format: mi_{type_prefix}_{hash8}."""
    raw = f"{run_id}|{entry_type}|{node_id or ''}|{phase_id or ''}|{discriminator}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    prefix = entry_type[:3]
    return f"mi_{prefix}_{h}"


def _truncate(s: str, max_len: int = MAX_DATA_CHARS_PER_ENTRY) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_phase_node_ids(phase: Dict[str, Any]) -> List[str]:
    """Get node IDs from a phase dict, handling both 'nodes' and 'node_ids' keys."""
    return phase.get("node_ids") or phase.get("nodes") or []


def transform_run_summary(
    run_id: str, state: Dict[str, Any], plan: Dict[str, Any],
    telemetry_summary: Optional[Dict[str, Any]] = None,
) -> List[IngestionEntry]:
    """Transform run-level data into a run_summary entry."""
    nodes = state.get("nodes", {})
    completed = sum(1 for n in nodes.values() if n.get("state") == "completed")
    failed = sum(1 for n in nodes.values() if n.get("state") == "failed")
    skill_sequence = []
    for phase in plan.get("phases", []):
        for nid in _get_phase_node_ids(phase):
            node_cfg = plan.get("nodes", {}).get(nid, {})
            sid = node_cfg.get("skill_id") or node_cfg.get("skill_name")
            if sid:
                skill_sequence.append(sid)
    data: Dict[str, Any] = {
        "status": state.get("status", "unknown"),
        "total_nodes": len(nodes),
        "nodes_completed": completed,
        "nodes_failed": failed,
        "phase_count": len(plan.get("phases", [])),
        "skill_sequence": skill_sequence[:20],
    }
    if telemetry_summary:
        data["total_duration_ms"] = telemetry_summary.get("total_duration_ms")
        data["total_tokens"] = telemetry_summary.get("total_tokens")
    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "run_summary"),
        entry_type="run_summary",
        source_path="state.json",
        timestamp=state.get("updated_at") or state.get("created_at") or _now_iso(),
        data=data,
    )]


def transform_skill_outcome(
    run_id: str, node_id: str, node_state: Dict[str, Any],
    result: Optional[Dict[str, Any]], plan: Dict[str, Any],
    selected_attempt: Optional[int] = None,
    final_attempt: Optional[int] = None,
) -> List[IngestionEntry]:
    """Transform a node result + state into a skill_outcome entry."""
    node_cfg = plan.get("nodes", {}).get(node_id, {})
    skill_id = node_cfg.get("skill_id") or node_cfg.get("skill_name")
    phase_id = node_cfg.get("phase_id")
    status = node_state.get("state", "unknown")
    attempt = node_state.get("attempt", 1)
    data: Dict[str, Any] = {"status": status, "attempt": attempt}
    started = node_state.get("started_at")
    completed = node_state.get("completed_at")
    if started and completed:
        data["started_at"] = started
        data["completed_at"] = completed
    if result:
        metrics = result.get("metrics", {})
        if metrics:
            data["metrics"] = {k: v for k, v in list(metrics.items())[:10]}
        outputs = result.get("outputs", result.get("output_files", []))
        if isinstance(outputs, (list, dict)):
            data["output_file_count"] = len(outputs)
    error = node_state.get("error")
    if error:
        if isinstance(error, dict):
            data["error_type"] = error.get("type", "unknown")
            data["error_message"] = _truncate(error.get("message", ""), 300)
        elif isinstance(error, str):
            data["error_message"] = _truncate(error, 300)

    # Annotate with best-attempt provenance when selected != final
    if selected_attempt is not None and final_attempt is not None and selected_attempt != final_attempt:
        data["best_attempt_number"] = selected_attempt
        data["final_attempt_number"] = final_attempt

    # Extract knowledge card usage (Package I3)
    if result:
        knowledge_cards = result.get("metrics", {}).get("knowledge_cards_used", [])
        if knowledge_cards:
            data["knowledge_cards_used"] = [
                {"card_id": c["card_id"], "source_id": c["source_id"],
                 "trust_level": c.get("trust_level")}
                for c in knowledge_cards[:10]
            ]

    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "skill_outcome", node_id=node_id),
        entry_type="skill_outcome",
        source_path=f"nodes/{node_id}/result.json",
        node_id=node_id, phase_id=phase_id, skill_id=skill_id,
        timestamp=completed or started or _now_iso(),
        data=data,
    )]


def transform_digest_entries(
    run_id: str, phase_id: str, digest: Dict[str, Any],
) -> List[IngestionEntry]:
    """Transform phase digest entries into digest_finding ingestion entries."""
    source_path = f"phases/{phase_id}/digest/phase_digest.json"
    results = []
    for entry in digest.get("entries", []):
        statement = entry.get("statement", "")
        digest_id = entry.get("digest_id", "")
        results.append(IngestionEntry(
            entry_id=generate_entry_id(run_id, "digest_finding", phase_id=phase_id,
                                       discriminator=digest_id or statement[:50]),
            entry_type="digest_finding",
            source_path=source_path,
            phase_id=phase_id,
            timestamp=digest.get("created_at", _now_iso()),
            data={
                "statement": _truncate(statement, 400),
                "type": entry.get("type", "fact"),
                "source_node_ids": entry.get("source_node_ids", []),
                "tags": entry.get("tags", [])[:5],
                "evidence_refs": entry.get("evidence_refs", [])[:10],
            },
            confidence=entry.get("confidence"),
        ))
    return results


def transform_validation(
    run_id: str, node_id: str, validation: Dict[str, Any],
    source_path: str, plan: Dict[str, Any],
) -> List[IngestionEntry]:
    """Transform a validation result into a validation_result entry."""
    node_cfg = plan.get("nodes", {}).get(node_id, {})
    skill_id = node_cfg.get("skill_id") or node_cfg.get("skill_name")
    phase_id = node_cfg.get("phase_id")
    checks = validation.get("checks", [])
    failed_checks = [c.get("check_id", "unknown") for c in checks if c.get("status") == "fail"]
    issues = validation.get("issues", [])
    data: Dict[str, Any] = {
        "score": validation.get("score"),
        "status": validation.get("status", "unknown"),
        "total_checks": len(checks),
        "failed_checks": failed_checks[:10],
        "issue_count": len(issues),
    }
    error_issues = [i for i in issues if i.get("severity") == "error"]
    if error_issues:
        data["top_errors"] = [_truncate(i.get("message", ""), 200) for i in error_issues[:3]]
    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "validation_result", node_id=node_id),
        entry_type="validation_result",
        source_path=source_path,
        node_id=node_id, phase_id=phase_id, skill_id=skill_id,
        timestamp=_now_iso(), data=data,
    )]


def transform_evidence_ledger(
    run_id: str, node_id: str, ledger: Dict[str, Any],
    source_path: str, plan: Dict[str, Any],
) -> List[IngestionEntry]:
    """Transform an evidence ledger into an evidence_summary entry."""
    node_cfg = plan.get("nodes", {}).get(node_id, {})
    skill_id = node_cfg.get("skill_id") or node_cfg.get("skill_name")
    phase_id = node_cfg.get("phase_id")
    entries = ledger.get("entries", [])
    total = len(entries)
    tools_used = list(set(e.get("tool_name", "unknown") for e in entries))
    ok_count = sum(1 for e in entries if e.get("status") == "ok")
    success_rate = ok_count / total if total > 0 else 0.0
    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "evidence_summary", node_id=node_id),
        entry_type="evidence_summary",
        source_path=source_path,
        node_id=node_id, phase_id=phase_id, skill_id=skill_id,
        timestamp=ledger.get("created_at", _now_iso()),
        data={
            "evidence_count": total, "tools_used": tools_used[:10],
            "success_rate": round(success_rate, 3),
            "ok_count": ok_count, "error_count": total - ok_count,
        },
    )]


def transform_phase_leader(
    run_id: str, phase_id: str, summary: Dict[str, Any], source_path: str,
) -> List[IngestionEntry]:
    """Transform a phase leader summary into a phase_leader_decision entry.

    Reads actual schema fields (leader_ran, issues_found, nodes_rerun, etc.)
    with defensive fallback to legacy field names (decision, reruns_triggered).
    """
    data: Dict[str, Any] = {}

    # Primary fields (actual PhaseLeader.write_summary() output)
    if "leader_ran" in summary:
        data["leader_ran"] = summary["leader_ran"]
        data["issues_found"] = summary.get("issues_found", 0)
        data["nodes_rerun"] = summary.get("nodes_rerun", [])[:10]
        data["reruns_succeeded"] = summary.get("reruns_succeeded", 0)
        data["reruns_failed"] = summary.get("reruns_failed", 0)
        data["phase_passed"] = summary.get("phase_passed", True)
        if summary.get("limits_applied"):
            data["limits_applied"] = summary["limits_applied"]
    # Legacy fallback (older format)
    elif "decision" in summary:
        data["decision"] = summary.get("decision", "unknown")
        data["reruns_triggered"] = summary.get("reruns_triggered", 0)
        rationale = summary.get("rationale") or summary.get("reasoning")
        if rationale:
            data["rationale"] = _truncate(str(rationale), 500)
        accepted = summary.get("accepted_nodes", [])
        rejected = summary.get("rejected_nodes", [])
        if accepted:
            data["accepted_nodes"] = accepted[:10]
        if rejected:
            data["rejected_nodes"] = rejected[:10]
    else:
        # Unknown format — store what we can
        data["raw_keys"] = sorted(summary.keys())[:10]

    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "phase_leader_decision", phase_id=phase_id),
        entry_type="phase_leader_decision",
        source_path=source_path, phase_id=phase_id,
        timestamp=summary.get("created_at", _now_iso()), data=data,
    )]


def transform_policy_usage(
    run_id: str, node_id: str, usage: Dict[str, Any],
    source_path: str, plan: Dict[str, Any],
) -> List[IngestionEntry]:
    """Transform policy usage data into a tool_usage_pattern entry.

    Reads actual fields (total_calls, total_seconds, per_tool) with
    defensive fallback to legacy field names (total_tool_calls, tool_call_counts).
    """
    node_cfg = plan.get("nodes", {}).get(node_id, {})
    skill_id = node_cfg.get("skill_id") or node_cfg.get("skill_name")
    phase_id = node_cfg.get("phase_id")
    data: Dict[str, Any] = {}

    # Primary fields (actual sandbox runtime output)
    if "total_calls" in usage:
        data["total_tool_calls"] = usage["total_calls"]
        data["total_seconds"] = usage.get("total_seconds", 0)
        per_tool = usage.get("per_tool", {})
        if per_tool:
            # per_tool is dict of {tool_name: {count, total_seconds}}
            data["tool_call_counts"] = {
                tool: (info.get("count", 0) if isinstance(info, dict) else info)
                for tool, info in list(per_tool.items())[:20]
            }
    # Legacy fallback
    elif "total_tool_calls" in usage:
        data["total_tool_calls"] = usage["total_tool_calls"]
        data["tool_call_counts"] = usage.get("tool_call_counts", {})
        budgets = usage.get("budgets_consumed", {})
        if budgets:
            data["budgets_consumed"] = budgets
    else:
        # Unknown format — store what we can
        data["raw_keys"] = sorted(usage.keys())[:10]

    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "tool_usage_pattern", node_id=node_id),
        entry_type="tool_usage_pattern",
        source_path=source_path,
        node_id=node_id, phase_id=phase_id, skill_id=skill_id,
        timestamp=_now_iso(), data=data,
    )]


def transform_policy_violations(
    run_id: str, node_id: str, violations: Dict[str, Any],
    source_path: str, plan: Dict[str, Any],
) -> List[IngestionEntry]:
    """Transform policy violations into a policy_violation entry."""
    node_cfg = plan.get("nodes", {}).get(node_id, {})
    skill_id = node_cfg.get("skill_id") or node_cfg.get("skill_name")
    phase_id = node_cfg.get("phase_id")
    violation_list = violations.get("violations", [])
    if not violation_list:
        return []
    return [IngestionEntry(
        entry_id=generate_entry_id(run_id, "policy_violation", node_id=node_id),
        entry_type="policy_violation",
        source_path=source_path,
        node_id=node_id, phase_id=phase_id, skill_id=skill_id,
        timestamp=_now_iso(),
        data={
            "violation_count": len(violation_list),
            "violations": [
                {"type": v.get("type", "unknown"), "tool": v.get("tool_name", "unknown"),
                 "message": _truncate(v.get("message", ""), 200)}
                for v in violation_list[:10]
            ],
        },
    )]


def transform_findings_pack_findings(
    run_id: str, phase_id: str, pack: Dict[str, Any],
) -> List[IngestionEntry]:
    """
    Transform findings pack entries into findings_pack_finding ingestion entries.

    Each entry carries provenance, validation metadata, and evidence flag
    from the findings pack, distinguishing them from raw digest_finding entries.
    """
    source_path = f"phases/{phase_id}/findings_pack/findings_pack.json"
    results = []
    for entry in pack.get("entries", []):
        statement = entry.get("statement", "")
        entry_id_str = entry.get("entry_id", "")
        provenance = entry.get("provenance", {})
        validation_meta = entry.get("validation_meta")
        evidenced = entry.get("evidenced", False)

        data: Dict[str, Any] = {
            "statement": _truncate(statement, 400),
            "type": entry.get("type", "fact"),
            "source_node_ids": entry.get("source_node_ids", []),
            "tags": entry.get("tags", [])[:5],
            "evidence_refs": entry.get("evidence_refs", [])[:10],
            "provenance": {
                "source_paths": provenance.get("source_paths", []),
                "extraction_method": provenance.get("extraction_method", "unknown"),
            },
            "evidenced": evidenced,
        }

        if validation_meta:
            data["validation_meta"] = {
                "score": validation_meta.get("score"),
                "status": validation_meta.get("status"),
            }

        results.append(IngestionEntry(
            entry_id=generate_entry_id(
                run_id, "findings_pack_finding", phase_id=phase_id,
                discriminator=entry_id_str or statement[:50],
            ),
            entry_type="findings_pack_finding",
            source_path=source_path,
            phase_id=phase_id,
            timestamp=pack.get("created_at", _now_iso()),
            data=data,
            confidence=entry.get("confidence"),
        ))
    return results
