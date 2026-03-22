"""
BrightMatter Supabase Client

Shared Supabase client used by worker.py, checkpoint_processor.py,
and any other module that needs to query the shared database.

Env vars:
    SUPABASE_URL              — Supabase project URL
    SUPABASE_KEY              — Supabase service role key (preferred)
    SUPABASE_SERVICE_ROLE_KEY — Alias for SUPABASE_KEY
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()


def get_supabase():
    """Get or create the singleton Supabase client.

    Raises ImportError if the ``supabase`` package is not installed.
    Raises ValueError if required env vars are missing.
    """
    global _client

    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client

        try:
            from supabase import create_client
        except ImportError:
            raise ImportError(
                "supabase package required. Install with: pip install supabase"
            )

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get(
            "SUPABASE_KEY",
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        )

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
                "must be set as environment variables."
            )

        _client = create_client(url, key)
        logger.info("Supabase client initialized")
        return _client


def get_supabase_or_none() -> Optional[object]:
    """Get the Supabase client, returning None on any failure."""
    try:
        return get_supabase()
    except (ImportError, ValueError) as e:
        logger.debug(f"Supabase unavailable: {e}")
        return None
