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

from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import HTMLResponse
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
    from lib.intelligence.types import Domain, validate_channel_context

    is_valid, msg = validate_channel_context(req.context)
    if not is_valid:
        logger.warning(f"Episode missing channel context: {msg}")

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
    processor = CheckpointProcessor(engine.storage, bridge)
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


# ── Dashboard ───────────────────────────────────────────────────────

@app.get("/api/v1/dashboard/data")
async def dashboard_data():
    """Public endpoint — returns live stats for the dashboard UI."""
    from lib.supabase_client import get_supabase
    db = get_supabase()

    ep_res = db.table("episodic_memory").select(
        "episode_id,skill_name,domain,weight,prediction_error,created_at"
    ).order("created_at", desc=True).limit(500).execute()
    episodes = ep_res.data or []

    pat_res = db.table("semantic_patterns").select(
        "pattern_id,skill_name,domain,confidence,evidence_count,"
        "successes,failures,recent_accuracy"
    ).execute()
    patterns = pat_res.data or []

    guid_res = db.table("guidance_cache").select(
        "skill_name,client_id,confidence"
    ).execute()
    guidance = guid_res.data or []

    wm_res = db.table("bm_watermarks").select("*").execute()
    watermarks = wm_res.data or []

    sig_res = db.table("signals").select("id", count="exact").limit(0).execute()
    ev_res = db.table("events").select("id", count="exact").limit(0).execute()

    skill_dist: Dict[str, int] = {}
    domain_dist: Dict[str, int] = {}
    for ep in episodes:
        s = ep.get("skill_name") or "unknown"
        d = ep.get("domain") or "generic"
        skill_dist[s] = skill_dist.get(s, 0) + 1
        domain_dist[d] = domain_dist.get(d, 0) + 1

    avg_conf = (
        sum(p.get("confidence") or 0 for p in patterns) / len(patterns)
        if patterns else 0
    )

    return {
        "episodes": episodes,
        "patterns": patterns,
        "guidance": guidance,
        "watermarks": watermarks,
        "signal_count": sig_res.count or 0,
        "event_count": ev_res.count or 0,
        "skill_dist": skill_dist,
        "domain_dist": domain_dist,
        "avg_confidence": avg_conf,
    }


@app.get("/api/v1/dashboard/feed")
async def dashboard_feed(limit: int = 80):
    """Returns a unified chronological activity feed in human language."""
    from lib.supabase_client import get_supabase
    db = get_supabase()

    feed: List[Dict[str, Any]] = []

    # ── Events (from MH-OS, Jarvis, etc.) ──
    ev_res = db.table("events").select(
        "id,source,event_type,skill_name,client_id,domain,result,context,metrics,created_at"
    ).order("created_at", desc=True).limit(40).execute()
    for e in (ev_res.data or []):
        src = e.get("source", "unknown")
        etype = e.get("event_type", "")
        result = e.get("result") or {}
        ctx = e.get("context") or {}
        metrics = e.get("metrics") or {}
        skill = e.get("skill_name", "unknown")
        domain = e.get("domain", "")

        if etype == "jarvis_episode":
            query = ctx.get("query_summary", "")
            tools = ctx.get("tools_used", [])
            cost = metrics.get("cost_usd", 0)
            sat = result.get("user_satisfaction")
            text = f"Jarvis: {query}" if query else "Jarvis ran a task"
            if tools:
                text += f" (used {', '.join(tools[:3])})"
            if cost > 0:
                text += f" — ${cost:.2f}"
            detail = f"jarvis / satisfaction: {sat}/5" if sat else "jarvis"
        elif etype == "skill_completed":
            summary = result.get("summary", "")
            text = summary or f"Completed {skill}"
            decisions = result.get("decisions", [])
            if decisions and not summary:
                text = decisions[0][:120] if isinstance(decisions[0], str) else str(decisions[0])[:120]
            detail = f"{src} / {skill} / {domain}" if domain else f"{src} / {skill}"
        else:
            text = result.get("summary", "") or f"{etype}: {skill}"
            detail = f"{src} / {domain}" if domain else src

        icon = "robot" if src == "jarvis" else "bolt"
        feed.append({
            "ts": e.get("created_at", ""),
            "type": "event",
            "icon": icon,
            "text": text,
            "detail": detail,
            "color": "cyan",
        })

    # ── Episodes ──
    ep_res = db.table("episodic_memory").select(
        "episode_id,skill_name,domain,prediction,outcome,weight,prediction_error,created_at"
    ).order("created_at", desc=True).limit(40).execute()
    seen_skills: Dict[str, int] = {}
    for ep in (ep_res.data or []):
        skill = ep.get("skill_name", "unknown")
        seen_skills[skill] = seen_skills.get(skill, 0) + 1
        if seen_skills[skill] > 4:
            continue
        ctx = (ep.get("prediction") or {}).get("context", {})
        meta = (ep.get("outcome") or {}).get("metadata", {})
        pe = ep.get("prediction_error") or 0
        channel = ctx.get("channel", "")
        source = ctx.get("source", "")
        spend = meta.get("spend")
        cpa = meta.get("cpa")

        ep_source = meta.get("_episode_source", "")
        icon = "brain"
        color = "purple"

        if source == "call_transcript":
            icon = "mic"
            color = "teal"
            transcript_id = meta.get("_transcript_id", "")[:8]
            if skill.startswith("call-strategy-recommendation"):
                ch_label = channel or skill.split(":")[-1] if ":" in skill else "channel"
                quotes = meta.get("quotes", [])
                text = f"CMO strategy rec for {ch_label}"
                if quotes:
                    text += f': "{quotes[0][:80]}…"' if len(quotes[0]) > 80 else f': "{quotes[0]}"'
            elif skill == "call-budget-reallocation":
                channels_list = ctx.get("channels_discussed", [])
                text = "Budget reallocation discussed"
                if channels_list:
                    text += f" ({', '.join(channels_list[:3])})"
            elif skill == "expert-observation":
                cs = meta.get("case_study", "")
                fw = meta.get("frameworks", [])
                text = f"Expert insight: {cs[:90]}" if cs else "Expert observation recorded"
                if fw:
                    text += f" [frameworks: {', '.join(fw[:2])}]"
            elif skill == "client-preference":
                pains = meta.get("pain_points", [])
                prefs = meta.get("preferences", [])
                items = pains[:2] + prefs[:2]
                text = "Client preference captured"
                if items:
                    text += f": {', '.join(str(i)[:40] for i in items)}"
            else:
                text = f"Transcript signal: {skill}"
            detail = f"call / {transcript_id}" if transcript_id else "call transcript"
        elif source == "bigquery-delta" and channel:
            parts = [f"Ingested {channel} daily data"]
            if spend is not None:
                parts[0] += f" (${spend:,.0f} spend)"
            if cpa is not None:
                parts.append(f"CPA ${cpa:,.0f}")
            text = " — ".join(parts)
            detail = f"{skill} / {ep.get('domain', 'generic')}"
        elif skill.startswith("cross-metric-correlation"):
            icon = "link"
            color = "orange"
            sig_type = meta.get("correlation_type", "")
            text = f"Cross-metric correlation: {sig_type}" if sig_type else "Multi-metric correlation detected"
            detail = f"correlation / {channel}" if channel else "correlation"
        elif skill == "daily-pulse":
            text = "Processed daily pulse observation"
            detail = f"{skill} / {ep.get('domain', 'generic')}"
        elif "signal" in str(ep.get("source") or ""):
            text = f"Learned from {skill} signal"
            detail = f"{skill} / {ep.get('domain', 'generic')}"
        else:
            text = f"Recorded {skill} episode"
            if pe and pe > 0.05:
                text += f" (prediction error: {pe:.1%})"
            detail = f"{skill} / {ep.get('domain', 'generic')}"

        feed.append({
            "ts": ep.get("created_at", ""),
            "type": "episode",
            "icon": icon,
            "text": text,
            "detail": detail,
            "color": color,
        })

    # ── Patterns ──
    pat_res = db.table("semantic_patterns").select(
        "pattern_id,skill_name,domain,confidence,evidence_count,successes,failures,updated_at,created_at"
    ).order("updated_at", desc=True).limit(20).execute()
    seen_pat_skills: Dict[str, int] = {}
    for p in (pat_res.data or []):
        skill = p.get("skill_name", "unknown")
        seen_pat_skills[skill] = seen_pat_skills.get(skill, 0) + 1
        if seen_pat_skills[skill] > 2:
            continue
        conf = p.get("confidence") or 0
        ev_count = p.get("evidence_count") or 0
        created = p.get("created_at", "")
        updated = p.get("updated_at", "")
        is_new = created == updated
        domain = p.get("domain", "generic")
        if is_new:
            text = f"New pattern: {skill}/{domain} ({conf:.0%} confidence, {ev_count} evidence)"
        else:
            text = f"Pattern strengthened: {skill}/{domain} → {conf:.0%} ({ev_count} evidence, {p.get('successes',0)} wins)"
        feed.append({
            "ts": updated,
            "type": "pattern",
            "icon": "sparkle",
            "text": text,
            "detail": f"{skill} / {domain}",
            "color": "gold",
        })

    # ── Guidance updates ──
    gu_res = db.table("guidance_cache").select(
        "skill_name,client_id,domain,confidence,expected_value,updated_at"
    ).order("updated_at", desc=True).limit(10).execute()
    seen_gu: Dict[str, int] = {}
    for g in (gu_res.data or []):
        skill = g.get("skill_name", "unknown")
        seen_gu[skill] = seen_gu.get(skill, 0) + 1
        if seen_gu[skill] > 2:
            continue
        conf = g.get("confidence") or 0
        text = f"Guidance refreshed: {skill} ({conf:.0%} confidence)"
        feed.append({
            "ts": g.get("updated_at", ""),
            "type": "guidance",
            "icon": "compass",
            "text": text,
            "detail": f"{skill} / {g.get('domain', 'generic')}",
            "color": "purple",
        })

    # ── Signals ──
    sig_res = db.table("signals").select(
        "id,date,source,lever,summary,created_at"
    ).order("created_at", desc=True).limit(15).execute()
    for s in (sig_res.data or []):
        text = s.get("summary") or f"Signal from {s.get('source', 'unknown')}"
        feed.append({
            "ts": s.get("created_at", ""),
            "type": "signal",
            "icon": "signal",
            "text": text,
            "detail": s.get("lever", ""),
            "color": "coral",
        })

    # ── Sync watermarks ──
    wm_res = db.table("bm_watermarks").select("*").execute()
    for w in (wm_res.data or []):
        src = (w.get("source") or "").upper()
        ts = w.get("last_processed_at", "")
        if ts:
            feed.append({
                "ts": w.get("updated_at", ts),
                "type": "sync",
                "icon": "sync",
                "text": f"Data stream synced: {src}",
                "detail": f"Last processed: {ts[:19]}",
                "color": "cyan",
            })

    feed.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return feed[:limit]


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the live dashboard HTML."""
    for base in [Path(__file__).parent, Path("/workspace")]:
        p = base / "dashboard.html"
        if p.exists():
            return HTMLResponse(p.read_text())
    raise HTTPException(status_code=404, detail="dashboard.html not found")
