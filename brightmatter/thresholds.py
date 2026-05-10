"""Loader for `config/thresholds.yaml` — the single source of truth for
detector thresholds with research provenance and tier/vertical overrides.

Usage:
    from brightmatter.thresholds import effective_thresholds
    th = effective_thresholds("brand_nonbrand_contamination",
                              business_type="ecommerce", spend_tier="<5k")
    if th is None:
        return  # detector skipped for this account
    if value > th["brand_roas_max"]:
        ...
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Threshold config missing at {CONFIG_PATH}. "
            f"Add it before running detectors that read from this loader."
        )
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


def _override_matches(when: dict, business_type: str | None, spend_tier: str | None) -> bool:
    """An override applies only if every condition in `when` matches the account."""
    if not when:
        return False
    if "business_type" in when and when["business_type"] != business_type:
        return False
    if "spend_tier" in when and when["spend_tier"] != spend_tier:
        return False
    return True


def effective_thresholds(
    detector_key: str,
    business_type: str | None = None,
    spend_tier: str | None = None,
) -> dict[str, Any] | None:
    """Return the effective threshold dict for this detector + account context.

    Returns None when an override matches with `skip: true` — the detector
    should not fire for accounts in that segment.
    """
    raw = _load_raw()
    detector = raw.get("detectors", {}).get(detector_key)
    if not detector:
        raise KeyError(f"No threshold config for detector '{detector_key}' in {CONFIG_PATH}")

    result = dict(detector.get("defaults", {}))
    for override in detector.get("overrides", []):
        if not _override_matches(override.get("when", {}), business_type, spend_tier):
            continue
        if override.get("skip") is True:
            return None
        for k, v in override.items():
            if k in ("when", "rationale", "source", "skip"):
                continue
            result[k] = v
    return result


def detector_description(detector_key: str) -> str:
    return _load_raw().get("detectors", {}).get(detector_key, {}).get("description", "")


def threshold_provenance(detector_key: str) -> list[dict]:
    """Return the source list for a detector — useful for explainability."""
    return _load_raw().get("detectors", {}).get(detector_key, {}).get("sources", [])
