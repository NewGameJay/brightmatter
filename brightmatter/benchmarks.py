"""Loader for `config/vertical_benchmarks.yaml` — external CPA benchmarks by
vertical (WordStream CPC/CVR), with quarterly seasonal adjustment.

Used by detect_vertical_cpa_benchmark as an absolute-market check, complementing
the segment-relative cross_account_outlier.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "vertical_benchmarks.yaml"


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Vertical-benchmark config missing at {CONFIG_PATH}.")
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


def benchmark_cpa(vertical: str) -> float | None:
    """Expected blended CPA ($) for a vertical, or None if not benchmarked."""
    return _load().get("benchmark_cpa", {}).get(vertical)


def seasonal_multiplier(quarter: int) -> float:
    """Quarterly multiplier on expected CPA (defaults to 1.0)."""
    return float(_load().get("seasonal_cpa_multiplier", {}).get(quarter, 1.0))


def detector_params() -> dict[str, Any]:
    return _load().get("detector", {})


_SEASONAL_PATH = Path(__file__).resolve().parent.parent / "config" / "seasonal_baselines.yaml"
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec")


@lru_cache(maxsize=1)
def _load_seasonal() -> dict[str, Any]:
    if not _SEASONAL_PATH.exists():
        return {}
    with _SEASONAL_PATH.open() as f:
        return yaml.safe_load(f) or {}


def seasonal_cpa_index(vertical: str, month: int) -> float:
    """Monthly CPA index (1.0 = annual avg) for a vertical; falls back to the
    default curve, then 1.0. month is 1–12."""
    s = _load_seasonal()
    key = _MONTHS[(month - 1) % 12]
    v = (s.get("verticals", {}) or {}).get(vertical)
    if v and key in v:
        return float(v[key])
    return float((s.get("default", {}) or {}).get(key, 1.0))
