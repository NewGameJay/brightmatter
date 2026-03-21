"""
BrightMatter Standalone API

Exposes the IntelligenceEngine via HTTP for consumption by:
- MH1HQ (skill execution integration)
- Jarvis (episode writing, guidance retrieval)
- Future clients

Run:
    uvicorn api:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger("brightmatter.api")


# ── Singleton engine ────────────────────────────────────────────────

_engine = None
_bridge = None


def _get_engine():
    global _engine
    if _engine is None:
        from lib.intelligence import IntelligenceEngine
        _engine = IntelligenceEngine()
        logger.info("IntelligenceEngine initialized")
    return _engine


def _get_bridge():
    global _bridge
    if _bridge is None:
        from lib.intelligence_bridge import IntelligenceBridge
        _bridge = IntelligenceBridge()
        logger.info("IntelligenceBridge initialized")
    return _bridge


# ── Auth ────────────────────────────────────────────────────────────

_API_KEY = os.getenv("BRIGHTMATTER_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_api_key(key: Optional[str] = Security(_api_key_header)):
    if not _API_KEY:
        return  # no key configured → open access (dev mode)
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Pydantic models ────────────────────────────────────────────────

class WriteEpisodeRequest(BaseModel):
    prediction_id: str = ""
    skill_name: str
    tenant_id: str
    domain: str = "generic"
    expected_signal: float = 1.0
    expected_baseline: float = 1.0
    observed_signal: float = 0.0
    observed_baseline: float = 1.0
    goal_completed: bool = False
    business_impact: float = 0.0
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JarvisEpisodeRequest(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)
    outcome: Dict[str, Any] = Field(default_factory=dict)
    episode_id: str = ""
    timestamp: str = ""
    tenant_id: str = "jarvis"


class GuidanceQuery(BaseModel):
    tenant_id: str
    domain: str = "generic"
    context: Dict[str, Any] = Field(default_factory=dict)


class RecordOutcomeRequest(BaseModel):
    prediction_id: str
    observed_signal: float
    observed_baseline: Optional[float] = None
    goal_completed: bool = False
    business_impact: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    prediction_id: str
    user_rating: float
    user_correction: Optional[str] = None


class StartTrackingRequest(BaseModel):
    skill_name: str
    client_id: str
    expected_signal: Optional[float] = None
    expected_baseline: Optional[float] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    guidance: Dict[str, Any] = Field(default_factory=dict)


class CompleteTrackingRequest(BaseModel):
    tracking_id: str
    observed_signal: float = 0.0
    goal_completed: bool = False
    business_impact: float = 0.0
    deferred: bool = False
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ModuleConsolidateRequest(BaseModel):
    module_id: str
    client_id: str
    execution_data: Dict[str, Any] = Field(default_factory=dict)


class ConsolidationRequest(BaseModel):
    tenant_id: Optional[str] = None


class PatternQuery(BaseModel):
    tenant_id: str = ""
    domain: str = "generic"


# ── Lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("BrightMatter API starting")
    _get_engine()
    yield
    logger.info("BrightMatter API shutting down")


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="BrightMatter Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Endpoints ───────────────────────────────────────────────────────

@app.get("/api/v1/health")
async def health():
    engine = _get_engine()
    return {
        "status": "ok",
        "engine": type(engine).__name__,
        "memory_layers": {
            "working": "active",
            "episodic": "active",
            "semantic": "active",
            "procedural": "active",
        },
    }


@app.post("/api/v1/episodes/write", dependencies=[Depends(_verify_api_key)])
async def write_episode(req: WriteEpisodeRequest):
    """Write a skill execution episode directly into the intelligence system."""
    engine = _get_engine()
    from lib.intelligence.types import Domain

    try:
        domain = Domain(req.domain)
    except ValueError:
        domain = Domain.GENERIC

    prediction_id = engine.register_prediction(
        skill_name=req.skill_name,
        tenant_id=req.tenant_id,
        domain=domain,
        expected_signal=req.expected_signal,
        expected_baseline=req.expected_baseline,
        context=req.context,
    )

    result = engine.record_outcome(
        prediction_id=prediction_id,
        observed_signal=req.observed_signal,
        observed_baseline=req.observed_baseline,
        goal_completed=req.goal_completed,
        business_impact=req.business_impact,
        metadata=req.metadata,
    )

    return {"prediction_id": prediction_id, "result": result}


@app.post("/api/v1/episodes/jarvis", dependencies=[Depends(_verify_api_key)])
async def write_jarvis_episode(req: JarvisEpisodeRequest):
    """Write a Jarvis-format episode."""
    engine = _get_engine()
    from lib.intelligence.jarvis_episodes import jarvis_episode_to_episodic

    raw: Dict[str, Any] = {
        "context": req.context,
        "outcome": req.outcome,
    }
    if req.episode_id:
        raw["episode_id"] = req.episode_id
    if req.timestamp:
        raw["timestamp"] = req.timestamp

    episode = jarvis_episode_to_episodic(raw, tenant_id=req.tenant_id)

    episodic_store = engine._episodic
    episode_id = episodic_store.store(episode)

    return {"episode_id": episode_id, "stored": True}


@app.get("/api/v1/guidance/{skill_name}", dependencies=[Depends(_verify_api_key)])
async def get_guidance(
    skill_name: str,
    tenant_id: str = "",
    domain: str = "generic",
):
    """Get pre-execution guidance for a skill."""
    engine = _get_engine()
    from lib.intelligence.types import Domain as DomainEnum

    try:
        d = DomainEnum(domain)
    except ValueError:
        d = DomainEnum.GENERIC

    guidance = engine.get_guidance(
        skill_name=skill_name,
        tenant_id=tenant_id,
        domain=d,
    )

    guidance_dict = guidance.to_dict() if hasattr(guidance, "to_dict") else {}

    return {
        "skill_name": skill_name,
        "guidance": guidance_dict,
        "prediction": {
            "predicted_outcome": guidance_dict.get("predicted_outcome"),
            "predicted_baseline": guidance_dict.get("predicted_baseline"),
            "pattern_expected_value": guidance_dict.get("pattern_expected_value"),
            "confidence": guidance_dict.get("confidence", 0.5),
            "is_exploration": guidance_dict.get("is_exploration", True),
        },
    }


@app.post("/api/v1/outcomes/record", dependencies=[Depends(_verify_api_key)])
async def record_outcome(req: RecordOutcomeRequest):
    """Record an observed outcome for a prediction."""
    engine = _get_engine()

    result = engine.record_outcome(
        prediction_id=req.prediction_id,
        observed_signal=req.observed_signal,
        observed_baseline=req.observed_baseline,
        goal_completed=req.goal_completed,
        business_impact=req.business_impact,
        metadata=req.metadata,
    )

    return {"prediction_id": req.prediction_id, "result": result}


@app.post("/api/v1/outcomes/feedback", dependencies=[Depends(_verify_api_key)])
async def record_feedback(req: FeedbackRequest):
    """Record user feedback on a prediction."""
    engine = _get_engine()

    result = engine.record_user_feedback(
        prediction_id=req.prediction_id,
        user_rating=req.user_rating,
        user_correction=req.user_correction,
    )

    return {"prediction_id": req.prediction_id, "result": result}


@app.post("/api/v1/consolidation/run", dependencies=[Depends(_verify_api_key)])
async def run_consolidation(req: ConsolidationRequest):
    """Trigger a memory consolidation cycle."""
    engine = _get_engine()

    stats = engine.run_consolidation(tenant_id=req.tenant_id)

    return {"status": "completed", "stats": stats}


@app.post("/api/v1/tracking/start", dependencies=[Depends(_verify_api_key)])
async def start_tracking(req: StartTrackingRequest):
    """Register a prediction and start tracking a skill execution."""
    bridge = _get_bridge()
    from lib.intelligence_bridge import SkillGuidance

    guidance_data = req.guidance or {}
    sg = SkillGuidance(
        parameters=guidance_data.get("parameters", {}),
        confidence=guidance_data.get("confidence", 0.5),
        expected_value=guidance_data.get("expected_value", 1.0),
        is_exploration=guidance_data.get("is_exploration", True),
        exploration_reason=guidance_data.get("exploration_reason", ""),
        patterns_used=guidance_data.get("patterns_used", []),
        predicted_outcome=guidance_data.get("predicted_outcome"),
        predicted_baseline=guidance_data.get("predicted_baseline"),
        pattern_expected_value=guidance_data.get("pattern_expected_value"),
    )

    tracking_id = bridge.start_tracking(
        skill_name=req.skill_name,
        client_id=req.client_id,
        guidance=sg,
        expected_signal=req.expected_signal,
        expected_baseline=req.expected_baseline,
        context=req.context,
    )

    return {"tracking_id": tracking_id}


@app.post("/api/v1/tracking/complete", dependencies=[Depends(_verify_api_key)])
async def complete_tracking(req: CompleteTrackingRequest):
    """Record outcome after execution and optionally defer learning."""
    bridge = _get_bridge()

    result = bridge.complete_tracking(
        tracking_id=req.tracking_id,
        result={"signal": req.observed_signal},
        metrics=req.metrics,
        goal_completed=req.goal_completed,
        business_impact=req.business_impact,
        deferred=req.deferred,
    )

    return {"tracking_id": req.tracking_id, "result": result.to_dict()}


@app.post("/api/v1/modules/consolidate", dependencies=[Depends(_verify_api_key)])
async def consolidate_module(req: ModuleConsolidateRequest):
    """Extract learnings from a completed module execution."""
    bridge = _get_bridge()

    stats = bridge.consolidate_from_module(
        module_id=req.module_id,
        client_id=req.client_id,
        execution_data=req.execution_data,
    )

    return {"status": "completed", "stats": stats}


@app.post("/api/v1/checkpoints/process", dependencies=[Depends(_verify_api_key)])
async def process_checkpoints():
    """Process all due outcome checkpoints. Called by cron."""
    bridge = _get_bridge()
    engine = _get_engine()
    from lib.intelligence.outcomes.checkpoint_processor import CheckpointProcessor
    processor = CheckpointProcessor(engine._firebase, bridge)
    results = processor.process_all_due()
    return {"status": "completed", "results": results}


@app.get("/api/v1/patterns/{skill_name}", dependencies=[Depends(_verify_api_key)])
async def get_patterns(
    skill_name: str,
    tenant_id: str = "",
    domain: str = "generic",
):
    """Get learned patterns for a skill."""
    engine = _get_engine()
    from lib.intelligence.types import Domain as DomainEnum

    try:
        d = DomainEnum(domain)
    except ValueError:
        d = DomainEnum.GENERIC

    semantic_store = engine._semantic

    patterns = []
    if hasattr(semantic_store, "retrieve"):
        raw_patterns = semantic_store.retrieve(
            skill_name=skill_name,
            domain=d,
            limit=20,
        )
        patterns = [
            p.to_dict() if hasattr(p, "to_dict") else str(p)
            for p in (raw_patterns or [])
        ]

    return {
        "skill_name": skill_name,
        "pattern_count": len(patterns),
        "patterns": patterns,
    }
