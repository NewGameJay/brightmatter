"""Base adapter and data structures for platform data ingestion."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DailyMetricRow:
    """Single day of aggregated metrics from a platform."""
    metric_date: date
    metrics: Dict[str, Any]
    record_count: int = 0
    breakdown: Optional[str] = None  # campaign name, flow name, etc.


@dataclass
class PlatformConfig:
    """Resolved credentials and settings for a platform pull."""
    platform: str
    client_id: str
    client_name: str
    credentials: Dict[str, Any] = field(default_factory=dict)
    account_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class BasePlatformAdapter(ABC):
    """ABC for platform-specific data adapters.

    Each subclass knows how to authenticate and pull daily aggregated
    metrics from one external platform.
    """

    PLATFORM: str = ""
    RATE_LIMIT_DELAY: float = 0.2  # seconds between API calls
    MAX_LOOKBACK_DAYS: int = 1095  # ~3 years default

    @abstractmethod
    def pull_daily_metrics(
        self,
        config: PlatformConfig,
        start_date: date,
        end_date: date,
    ) -> List[DailyMetricRow]:
        """Pull aggregated metrics for each day in the range.

        Returns one DailyMetricRow per day (or per day/breakdown combo).
        Implementations must handle their own pagination and rate limiting.
        """
        ...

    def platform_name(self) -> str:
        return self.PLATFORM

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _safe_float(v: Any) -> float:
        if v is None:
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_int(v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0
