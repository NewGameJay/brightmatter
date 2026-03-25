"""Per-platform rate limiter for API calls."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)

# Delay in seconds between consecutive API calls per platform
PLATFORM_DELAYS: Dict[str, float] = {
    "google_ads": 0.5,
    "meta_ads": 0.5,
    "klaviyo": 0.15,
    "hubspot": 0.12,
    "shopify": 0.5,
    "braze": 0.2,
    "iterable": 0.2,
    "beehiiv": 0.3,
    "triple_whale": 0.3,
    "amplitude": 0.2,
    "customerio": 0.2,
    "appsflyer": 0.3,
}

# Delay between switching from one client account to the next on the same platform
INTER_ACCOUNT_DELAY: Dict[str, float] = {
    "google_ads": 5.0,
    "meta_ads": 5.0,
}

# For backfills, use longer delays to avoid exhausting daily quotas
BACKFILL_MULTIPLIER = 3.0


class RateLimiter:
    """Thread-safe per-platform rate limiter."""

    def __init__(self, *, backfill: bool = False):
        self._lock = threading.Lock()
        self._last_call: Dict[str, float] = defaultdict(float)
        self._backfill = backfill

    def wait(self, platform: str) -> None:
        delay = PLATFORM_DELAYS.get(platform, 0.2)
        if self._backfill:
            delay *= BACKFILL_MULTIPLIER
        with self._lock:
            elapsed = time.monotonic() - self._last_call[platform]
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_call[platform] = time.monotonic()

    def inter_account_wait(self, platform: str) -> None:
        delay = INTER_ACCOUNT_DELAY.get(platform, 1.0)
        if self._backfill:
            delay *= BACKFILL_MULTIPLIER
        time.sleep(delay)
