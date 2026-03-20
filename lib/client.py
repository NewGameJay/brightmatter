"""
BrightMatter HTTP Client

Thin client for MH1HQ and Jarvis to call the BrightMatter API
instead of importing IntelligenceEngine directly.

Usage:
    from lib.client import BrightMatterClient

    bm = BrightMatterClient(base_url="http://localhost:8100", api_key="...")

    # Get guidance before skill execution
    guidance = bm.get_guidance("lifecycle-audit", tenant_id="acme")

    # Write a skill episode
    result = bm.write_episode(
        skill_name="lifecycle-audit",
        tenant_id="acme",
        observed_signal=0.8,
        goal_completed=True,
    )

    # Write a Jarvis episode
    bm.write_jarvis_episode(
        context={"trigger": "interactive", "query_summary": "..."},
        outcome={"goal_completed": True, "user_satisfaction": 4},
    )

    # Trigger consolidation
    stats = bm.run_consolidation()
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = os.getenv("BRIGHTMATTER_URL", "http://localhost:8100")
_DEFAULT_API_KEY = os.getenv("BRIGHTMATTER_API_KEY", "")


class BrightMatterClient:
    """HTTP client for the BrightMatter API.

    Uses only stdlib ``urllib`` to avoid adding ``httpx`` or ``requests``
    as a hard dependency for callers.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = _DEFAULT_API_KEY,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items() if v)
            if qs:
                url += f"?{qs}"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            logger.error(f"BrightMatter API error {e.code}: {error_body}")
            raise
        except URLError as e:
            logger.error(f"BrightMatter API unreachable: {e.reason}")
            raise

    # ── Episode endpoints ───────────────────────────────────────────

    def write_episode(
        self,
        skill_name: str,
        tenant_id: str,
        observed_signal: float = 0.0,
        goal_completed: bool = False,
        domain: str = "generic",
        expected_signal: float = 1.0,
        expected_baseline: float = 1.0,
        observed_baseline: float = 1.0,
        business_impact: float = 0.0,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/episodes/write", body={
            "skill_name": skill_name,
            "tenant_id": tenant_id,
            "domain": domain,
            "expected_signal": expected_signal,
            "expected_baseline": expected_baseline,
            "observed_signal": observed_signal,
            "observed_baseline": observed_baseline,
            "goal_completed": goal_completed,
            "business_impact": business_impact,
            "context": context or {},
            "metadata": metadata or {},
        })

    def write_jarvis_episode(
        self,
        context: Dict[str, Any],
        outcome: Dict[str, Any],
        episode_id: str = "",
        timestamp: str = "",
        tenant_id: str = "jarvis",
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/episodes/jarvis", body={
            "context": context,
            "outcome": outcome,
            "episode_id": episode_id,
            "timestamp": timestamp,
            "tenant_id": tenant_id,
        })

    # ── Guidance ────────────────────────────────────────────────────

    def get_guidance(
        self,
        skill_name: str,
        tenant_id: str = "",
        domain: str = "generic",
    ) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/guidance/{skill_name}", params={
            "tenant_id": tenant_id,
            "domain": domain,
        })

    # ── Outcomes ────────────────────────────────────────────────────

    def record_outcome(
        self,
        prediction_id: str,
        observed_signal: float,
        observed_baseline: Optional[float] = None,
        goal_completed: bool = False,
        business_impact: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "prediction_id": prediction_id,
            "observed_signal": observed_signal,
            "goal_completed": goal_completed,
            "business_impact": business_impact,
            "metadata": metadata or {},
        }
        if observed_baseline is not None:
            body["observed_baseline"] = observed_baseline
        return self._request("POST", "/api/v1/outcomes/record", body=body)

    def record_feedback(
        self,
        prediction_id: str,
        user_rating: float,
        user_correction: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "prediction_id": prediction_id,
            "user_rating": user_rating,
        }
        if user_correction is not None:
            body["user_correction"] = user_correction
        return self._request("POST", "/api/v1/outcomes/feedback", body=body)

    # ── Consolidation ───────────────────────────────────────────────

    def run_consolidation(
        self,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/consolidation/run", body={
            "tenant_id": tenant_id,
        })

    # ── Patterns ────────────────────────────────────────────────────

    def get_patterns(
        self,
        skill_name: str,
        tenant_id: str = "",
        domain: str = "generic",
    ) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/patterns/{skill_name}", params={
            "tenant_id": tenant_id,
            "domain": domain,
        })

    # ── Health ──────────────────────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/health")
