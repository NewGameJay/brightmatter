"""
Adapter from ingestion bundle to the consolidation manager interface.

Maps the structured ingestion bundle into the execution_data format
expected by IntelligenceBridge.consolidate_from_module().

Enriches checkpoint output with validation scores, evidence counts,
policy violations, skill category, and execution shape identifiers
so that _create_skill_episode() can produce meaningful episodic memories.
"""

from typing import Any, Dict, List, Optional

from .transform import _get_phase_node_ids


def _extract_skill_category(skill_path: str) -> Optional[str]:
    """Extract skill category from skill_path (e.g. 'skills/search-skills/...' -> 'search-skills')."""
    if not skill_path:
        return None
    parts = skill_path.strip("/").split("/")
    # Expected format: skills/<category>/<skill-name>/...
    if len(parts) >= 2 and parts[0] == "skills":
        return parts[1]
    return None


def adapt_bundle_to_execution_data(
    bundle: Dict[str, Any],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Adapt an ingestion bundle into the execution_data format
    expected by consolidate_from_module().
    """
    entries = bundle.get("entries", [])

    skill_plan = []
    for phase in plan.get("phases", []):
        for nid in _get_phase_node_ids(phase):
            node_cfg = plan.get("nodes", {}).get(nid, {})
            sid = node_cfg.get("skill_id") or node_cfg.get("skill_name")
            if sid:
                skill_plan.append(sid)

    # Index entries by node_id for fast lookup
    entries_by_node: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        nid = e.get("node_id")
        if nid:
            entries_by_node.setdefault(nid, []).append(e)

    checkpoints = []
    skill_outcome_entries = [e for e in entries if e.get("entry_type") == "skill_outcome"]
    for i, entry in enumerate(skill_outcome_entries):
        data = entry.get("data", {})
        node_id = entry.get("node_id", "")
        skill_id = entry.get("skill_id") or ""
        status = data.get("status", "unknown")
        checkpoint_status = "success" if status == "completed" else "failed"

        node_entries = [e for e in entries_by_node.get(node_id, []) if e != entry]

        # Build enriched output dict
        output: Dict[str, Any] = {
            "metrics": data.get("metrics", {}),
            "output_file_count": data.get("output_file_count", 0),
        }

        # Enrich with validation score
        val_entries = [e for e in node_entries if e.get("entry_type") == "validation_result"]
        if val_entries:
            val_data = val_entries[0].get("data", {})
            score = val_data.get("score")
            if score is not None:
                output["validation_score"] = score
            output["validation_status"] = val_data.get("status")

        # Enrich with evidence count
        ev_entries = [e for e in node_entries if e.get("entry_type") == "evidence_summary"]
        if ev_entries:
            ev_data = ev_entries[0].get("data", {})
            output["evidence_count"] = ev_data.get("evidence_count", 0)

        # Enrich with policy violations count
        pv_entries = [e for e in node_entries if e.get("entry_type") == "policy_violation"]
        if pv_entries:
            pv_data = pv_entries[0].get("data", {})
            output["policy_violations"] = pv_data.get("violation_count", 0)

        # Enrich with tool usage
        tu_entries = [e for e in node_entries if e.get("entry_type") == "tool_usage_pattern"]
        if tu_entries:
            tu_data = tu_entries[0].get("data", {})
            output["total_tool_calls"] = tu_data.get("total_tool_calls", 0)

        # Extract skill category from plan node config
        node_cfg = plan.get("nodes", {}).get(node_id, {})
        skill_path = node_cfg.get("skill_path", "")
        category = _extract_skill_category(skill_path)
        if category:
            output["skill_category"] = category

        # Execution shape identifiers (stable, bounded)
        tool_policy = node_cfg.get("tool_policy_mode")
        if tool_policy:
            output["tool_policy_mode"] = str(tool_policy)[:50]
        evidence_mode = node_cfg.get("evidence_mode")
        if evidence_mode:
            output["evidence_mode"] = str(evidence_mode)[:50]
        if node_cfg.get("output_schema"):
            output["schema_present"] = True
        attempt_count = data.get("attempt", 1)
        output["attempt_count"] = attempt_count

        # Explicit domain if present in node config
        explicit_domain = node_cfg.get("domain")
        if explicit_domain:
            output["domain"] = str(explicit_domain)[:50]

        checkpoints.append({
            "skill_name": skill_id,
            "skill_index": i,
            "status": checkpoint_status,
            "output": output,
            "error": data.get("error_message"),
            "ingestion_entries": node_entries,
        })

    run_summaries = [e for e in entries if e.get("entry_type") == "run_summary"]
    overall_error = None
    outputs: Dict[str, Any] = {}
    if run_summaries:
        rs_data = run_summaries[0].get("data", {})
        if rs_data.get("status") == "failed":
            overall_error = f"Run failed: {rs_data.get('nodes_failed', 0)} nodes failed"
        outputs["skill_sequence"] = rs_data.get("skill_sequence", [])
        outputs["total_nodes"] = rs_data.get("total_nodes", 0)
        outputs["nodes_completed"] = rs_data.get("nodes_completed", 0)
        outputs["nodes_failed"] = rs_data.get("nodes_failed", 0)

    digest_entries = [e for e in entries if e.get("entry_type") == "digest_finding"]
    if digest_entries:
        outputs["digest_findings_count"] = len(digest_entries)

    # Findings pack quality metrics (Package I1)
    fp_entries = [e for e in entries if e.get("entry_type") == "findings_pack_finding"]
    if fp_entries:
        outputs["findings_pack_count"] = len(fp_entries)
        outputs["findings_pack_evidenced_count"] = sum(
            1 for e in fp_entries if e.get("data", {}).get("evidenced")
        )
        outputs["findings_pack_avg_confidence"] = (
            sum(e.get("confidence") or 0 for e in fp_entries) / len(fp_entries)
        )

    return {
        "skill_plan": skill_plan,
        "checkpoints": checkpoints,
        "outputs": outputs,
        "error": overall_error,
        "ingestion_bundle_version": bundle.get("version", "1"),
        "run_id": bundle.get("run_id", ""),
        "module_id": bundle.get("module_id", ""),
    }
