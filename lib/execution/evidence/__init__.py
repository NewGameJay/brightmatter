"""
Evidence Mode — Structured evidence capture and validation.

Captures tool-call evidence into structured artifacts with stable IDs,
validates output citations, and supports warn-only or strict enforcement.

Components:
- ledger: Evidence ledger creation, entry management, serialization
- redaction: Sanitize sensitive fields from evidence artifacts
- hash_utils: SHA-256 hashing for raw artifact integrity
"""

from lib.execution.evidence.ledger import (
    EvidenceLedger,
    EvidenceEntry,
    init_evidence_dir,
    write_ledger,
    load_ledger,
)
from lib.execution.evidence.redaction import redact_tool_input, redact_headers
from lib.execution.evidence.hash_utils import compute_sha256, compute_sha256_str

__all__ = [
    "EvidenceLedger",
    "EvidenceEntry",
    "init_evidence_dir",
    "write_ledger",
    "load_ledger",
    "redact_tool_input",
    "redact_headers",
    "compute_sha256",
    "compute_sha256_str",
]
