"""
BrightMatter Remote Bridge

Drop-in replacement for ``IntelligenceBridge`` that routes all calls
through the BrightMatter HTTP API.  Used by MH1HQ execution engine
and Jarvis during the transition from direct imports to API-based
integration.

Usage in MH1HQ engine.py:

    # Replace:
    #   from lib.intelligence_bridge import IntelligenceBridge
    # With:
    #   from lib.remote_bridge import RemoteIntelligenceBridge as IntelligenceBridge

    bridge = IntelligenceBridge()
    guidance = bridge.get_skill_guidance("lifecycle-audit", "acme-corp")

The bridge is also importable as a standalone file — copy it into the
MH1HQ repo at ``lib/brightmatter_bridge.py`` and configure via env:

    BRIGHTMATTER_URL=http://localhost:8100
    BRIGHTMATTER_API_KEY=your-key
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


class _SkillGuidance:
    """Lightweight guidance container matching IntelligenceBridge.SkillGuidance."""
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.skill_name = data.get("skill_name", "")
        self.prediction = data.get("prediction", {})
        self.recommendations = data.get("recommendations", [])
        self.patterns = data.get("patterns", [])
        self.procedural = data.get("procedural", [])
        self.recent_performance = data.get("recent_performance", {})

    def to_dict(self) -> Dict[str, Any]:
        return self._data


class RemoteIntelligenceBridge:
    """API-backed IntelligenceBridge replacement.

    Provides the same public methods as ``IntelligenceBridge`` but sends
    requests to the BrightMatter API instead of importing the engine.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or os.getenv("BRIGHTMATTER_URL", "http://localhost:8100")).rstrip("/")
        self.api_key = api_key or os.getenv("BRIGHTMATTER_API_KEY", "")
        self.timeout = timeout
        self._tracking: Dict[str, Dict[str, Any]] = {}
        logger.info(f"RemoteIntelligenceBridge initialized → {self.base_url}")

    def _request(self, method: str, path: str, body=None, params=None):
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
        except (HTTPError, URLError) as e:
            logger.error(f"BrightMatter API call failed: {e}")
            return {}

    def get_skill_guidance(
        self,
        skill_name: str,
        client_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> _SkillGuidance:
        resp = self._request("GET", f"/api/v1/guidance/{skill_name}", params={
            "tenant_id": client_id,
        })
        guidance_data = resp.get("guidance", {})
        if isinstance(guidance_data, str):
            guidance_data = {"raw": guidance_data}
        guidance_data["skill_name"] = skill_name
        return _SkillGuidance(guidance_data)

    def start_tracking(
        self,
        skill_name: str,
        client_id: str,
        guidance: Any = None,
        expected_signal: Optional[float] = None,
        expected_baseline: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        guidance_dict = {}
        if guidance is not None:
            if hasattr(guidance, "to_dict"):
                guidance_dict = guidance.to_dict()
            elif isinstance(guidance, dict):
                guidance_dict = guidance

        resp = self._request("POST", "/api/v1/tracking/start", body={
            "skill_name": skill_name,
            "client_id": client_id,
            "expected_signal": expected_signal,
            "expected_baseline": expected_baseline,
            "context": context or {},
            "guidance": guidance_dict,
        })
        tracking_id = resp.get("tracking_id", str(uuid.uuid4())[:12])

        self._tracking[tracking_id] = {
            "skill_name": skill_name,
            "client_id": client_id,
            "expected_signal": expected_signal,
            "expected_baseline": expected_baseline,
            "context": context or {},
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return tracking_id

    def complete_tracking(
        self,
        tracking_id: str,
        observed_signal: float = 0.0,
        goal_completed: bool = False,
        result: Optional[Dict[str, Any]] = None,
        deferred: bool = False,
        business_impact: float = 0.0,
        **kwargs,
    ) -> Dict[str, Any]:
        self._tracking.pop(tracking_id, {})

        resp = self._request("POST", "/api/v1/tracking/complete", body={
            "tracking_id": tracking_id,
            "observed_signal": observed_signal,
            "goal_completed": goal_completed,
            "business_impact": business_impact,
            "deferred": deferred,
            "metrics": kwargs,
        })
        return resp

    def close_deferred_outcome(
        self,
        prediction_id: str,
        client_id: str = "",
        observed_signal: float = 0.0,
        business_impact: float = 0.0,
        platform_metrics: Optional[Dict[str, Any]] = None,
        projection_classification: Optional[str] = None,
        observed_baseline: Optional[float] = None,
        goal_completed: bool = False,
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/outcomes/record", body={
            "prediction_id": prediction_id,
            "observed_signal": observed_signal,
            "observed_baseline": observed_baseline,
            "goal_completed": goal_completed,
            "business_impact": business_impact,
            "metadata": {
                "_platform_metrics": platform_metrics or {},
                "_projection_classification": projection_classification,
            },
        })

    def consolidate_from_module(
        self,
        module_id: str,
        client_id: str,
        execution_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/modules/consolidate", body={
            "module_id": module_id,
            "client_id": client_id,
            "execution_data": execution_data or {},
        })

    def process_checkpoints(self) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/checkpoints/process")

    def run_consolidation(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/consolidation/run", body={
            "tenant_id": tenant_id,
        })

    def write_jarvis_episode(
        self,
        context: Dict[str, Any],
        outcome: Dict[str, Any],
        tenant_id: str = "jarvis",
    ) -> Dict[str, Any]:
        return self._request("POST", "/api/v1/episodes/jarvis", body={
            "context": context,
            "outcome": outcome,
            "tenant_id": tenant_id,
        })
