"""
Memory Health Check — Production verification for MH1 intelligence memory layers.

Connects to Firebase and queries each memory collection to verify data is
actually being persisted. Reports counts, timestamps, and connectivity status.

Usage:
    python3 -m lib.memory_health          # Run from project root
    mh1 memory-health                     # Via CLI
    mh1 memory-health --json              # Machine-readable output
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LayerReport:
    """Health report for a single memory layer."""
    name: str
    firebase_path: str
    connected: bool = False
    doc_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if not self.connected:
            return "no_firebase"
        return "ok"


@dataclass
class MemoryHealthReport:
    """Complete memory health report."""
    firebase_connected: bool = False
    firebase_type: str = "unknown"
    project_id: str = ""
    layers: List[LayerReport] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.firebase_connected and all(l.status == "ok" for l in self.layers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "firebase_connected": self.firebase_connected,
            "firebase_type": self.firebase_type,
            "project_id": self.project_id,
            "overall": "ok" if self.ok else "degraded",
            "checked_at": self.checked_at,
            "error": self.error,
            "layers": [
                {
                    "name": l.name,
                    "firebase_path": l.firebase_path,
                    "status": l.status,
                    "doc_count": l.doc_count,
                    "details": l.details,
                    "error": l.error,
                }
                for l in self.layers
            ],
        }


def _safe_count(fb, collection_path: str, limit: int = 500) -> tuple[int, list]:
    """Count docs in a collection, returning (count, sample_docs)."""
    try:
        docs = fb.get_collection(collection=collection_path, limit=limit)
        if docs is None:
            return 0, []
        doc_list = list(docs) if not isinstance(docs, list) else docs
        return len(doc_list), doc_list[:5]
    except Exception as e:
        raise RuntimeError(f"Query failed on {collection_path}: {e}")


def _newest_timestamp(docs: list, ts_fields: list[str]) -> Optional[str]:
    """Find the most recent timestamp across a list of docs."""
    latest = None
    for doc in docs:
        d = doc if isinstance(doc, dict) else (doc.to_dict() if hasattr(doc, "to_dict") else {})
        for f in ts_fields:
            val = d.get(f)
            if val and isinstance(val, str):
                if latest is None or val > latest:
                    latest = val
    return latest


def check_episodic(fb) -> LayerReport:
    """Check episodic memory: system/intelligence/episodic/{tenant}/{skill}."""
    report = LayerReport(
        name="episodic",
        firebase_path="system/intelligence/episodic",
        connected=True,
    )
    try:
        base = "system/intelligence/episodic"
        tenants = fb.get_collection(collection=base, limit=100)
        tenant_list = list(tenants) if tenants else []

        total_episodes = 0
        tenant_skills: Dict[str, List[str]] = {}

        has_list_subcollections = hasattr(fb, "list_subcollections")

        for tenant_doc in tenant_list:
            tid = tenant_doc.get("_id", "") if isinstance(tenant_doc, dict) else ""
            if not tid:
                continue
            doc_path = f"{base}/{tid}"
            try:
                if has_list_subcollections:
                    skill_names = fb.list_subcollections(doc_path)
                else:
                    skill_names = []

                for sid in skill_names:
                    ep_path = f"{base}/{tid}/{sid}"
                    try:
                        count, samples = _safe_count(fb, ep_path, limit=200)
                        total_episodes += count
                    except Exception:
                        pass
                tenant_skills[tid] = skill_names
            except Exception:
                pass

        report.doc_count = total_episodes
        report.details = {
            "tenants": len(tenant_skills),
            "tenant_skills": {k: len(v) for k, v in tenant_skills.items()},
        }
        if total_episodes == 0 and len(tenant_list) == 0:
            report.details["note"] = "No episodic data found — memory consolidation may not have run yet"
    except Exception as e:
        report.error = str(e)
    return report


def check_semantic(fb) -> LayerReport:
    """Check semantic memory: system/intelligence/semantic/{domain}/patterns."""
    from lib.intelligence.types import Domain

    report = LayerReport(
        name="semantic",
        firebase_path="system/intelligence/semantic",
        connected=True,
    )
    try:
        total_patterns = 0
        domain_counts: Dict[str, int] = {}

        for domain in Domain:
            path = f"system/intelligence/semantic/{domain.value}/patterns"
            try:
                count, samples = _safe_count(fb, path)
                domain_counts[domain.value] = count
                total_patterns += count
            except Exception:
                domain_counts[domain.value] = 0

        report.doc_count = total_patterns
        report.details = {"by_domain": domain_counts}
        if total_patterns == 0:
            report.details["note"] = "No semantic patterns — episodic memories need consolidation first"
    except Exception as e:
        report.error = str(e)
    return report


def check_procedural(fb) -> LayerReport:
    """Check procedural memory: system/intelligence/procedural."""
    report = LayerReport(
        name="procedural",
        firebase_path="system/intelligence/procedural",
        connected=True,
    )
    try:
        count, samples = _safe_count(fb, "system/intelligence/procedural")
        report.doc_count = count
        newest = _newest_timestamp(samples, ["_updated_at", "_created_at", "created_at"])
        report.details = {"last_updated": newest}
        if count == 0:
            report.details["note"] = "No procedural knowledge — requires multiple consolidated semantic patterns"
    except Exception as e:
        report.error = str(e)
    return report


def check_shadow(fb) -> LayerReport:
    """Check shadow testing state: system/intelligence/shadow_state."""
    report = LayerReport(
        name="shadow",
        firebase_path="system/intelligence/shadow_state",
        connected=True,
    )
    try:
        count, samples = _safe_count(fb, "system/intelligence/shadow_state")
        report.doc_count = count
        report.details = {}
    except Exception as e:
        report.error = str(e)
    return report


def check_accuracy(fb) -> LayerReport:
    """Check accuracy reports: system/intelligence/accuracy_reports."""
    report = LayerReport(
        name="accuracy_reports",
        firebase_path="system/intelligence/accuracy_reports",
        connected=True,
    )
    try:
        count, samples = _safe_count(fb, "system/intelligence/accuracy_reports")
        report.doc_count = count
        newest = _newest_timestamp(samples, ["_updated_at", "_created_at", "scored_at"])
        report.details = {"last_scored": newest}
    except Exception as e:
        report.error = str(e)
    return report


def run_memory_health() -> MemoryHealthReport:
    """Run a full memory health check against production Firebase."""
    report = MemoryHealthReport()

    try:
        from lib.firebase_client import get_firebase_client, FirebaseClient
        fb = get_firebase_client()
        report.firebase_connected = True
        report.firebase_type = type(fb).__name__

        if isinstance(fb, FirebaseClient):
            report.project_id = getattr(fb, "_project_id", "")
        else:
            report.firebase_type = f"{type(fb).__name__} (possibly mock)"

    except ImportError:
        report.error = "lib.firebase_client not importable"
        return report
    except Exception as e:
        report.error = f"Firebase init failed: {e}"
        return report

    connectivity_ok = False
    try:
        fb.get_collection(collection="clients", limit=1)
        connectivity_ok = True
    except Exception as e:
        report.error = f"Firebase connectivity test failed: {e}"
        report.firebase_connected = False
        return report

    if not connectivity_ok:
        return report

    report.layers = [
        check_episodic(fb),
        check_semantic(fb),
        check_procedural(fb),
        check_shadow(fb),
        check_accuracy(fb),
    ]

    return report


def print_report(report: MemoryHealthReport, use_json: bool = False) -> None:
    """Print the report in human-readable or JSON format."""
    if use_json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    print()
    print("=" * 55)
    print("  MH1 Memory Health Check")
    print("=" * 55)
    print()

    status_char = "OK" if report.firebase_connected else "FAIL"
    print(f"  Firebase:   {status_char}  ({report.firebase_type})")
    print(f"  Project:    {report.project_id or '(unknown)'}")
    if report.error:
        print(f"  Error:      {report.error}")
    print()

    if not report.layers:
        print("  No layers checked (Firebase unavailable)")
        print()
        return

    print(f"  {'Layer':<20} {'Status':<12} {'Docs':<8} Notes")
    print(f"  {'-'*20} {'-'*12} {'-'*8} {'-'*30}")

    for layer in report.layers:
        status = layer.status.upper()
        notes = ""
        if layer.error:
            notes = layer.error[:40]
        elif layer.details.get("note"):
            notes = layer.details["note"][:40]
        elif layer.name == "episodic":
            tenants = layer.details.get("tenants", 0)
            notes = f"{tenants} tenant(s)"
        elif layer.name == "semantic":
            by_domain = layer.details.get("by_domain", {})
            non_zero = {k: v for k, v in by_domain.items() if v > 0}
            if non_zero:
                notes = ", ".join(f"{k}:{v}" for k, v in non_zero.items())
            else:
                notes = "empty"
        elif layer.details.get("last_updated") or layer.details.get("last_scored"):
            ts = layer.details.get("last_updated") or layer.details.get("last_scored")
            notes = f"last: {ts[:19]}" if ts else ""

        print(f"  {layer.name:<20} {status:<12} {layer.doc_count:<8} {notes}")

    print()

    total_docs = sum(l.doc_count for l in report.layers)
    errors = sum(1 for l in report.layers if l.status == "error")

    if total_docs == 0:
        print("  VERDICT: Memory system is EMPTY.")
        print("  The intelligence learning loop has not persisted any data.")
        print("  Run a module to seed episodic memory, then consolidate.")
    elif errors > 0:
        print(f"  VERDICT: {errors} layer(s) have errors. Check details above.")
    else:
        print(f"  VERDICT: Memory system is ACTIVE ({total_docs} total documents).")
    print()


def main(args: list[str] | None = None) -> int:
    """CLI entrypoint for mh1 memory-health."""
    import argparse

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        prog="mh1 memory-health",
        description="Check MH1 intelligence memory layer health against Firebase",
    )
    parser.add_argument("--json", dest="use_json", action="store_true", help="Output JSON")
    parsed = parser.parse_args(args or [])

    report = run_memory_health()
    print_report(report, use_json=parsed.use_json)
    return 0 if report.ok or (report.firebase_connected and not report.error) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
