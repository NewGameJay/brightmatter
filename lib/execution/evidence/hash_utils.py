"""
Evidence Mode — Hashing utilities.

Provides SHA-256 hashing for raw evidence artifacts.
"""

import hashlib
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Lowercase hex digest string (64 chars).
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_sha256_str(content: str) -> str:
    """
    Compute SHA-256 hash of a string.

    Args:
        content: String content to hash.

    Returns:
        Lowercase hex digest string (64 chars).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
