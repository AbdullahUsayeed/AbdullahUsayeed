"""
System Link — FastAPI Application
===================================
Exposes the simulation pipeline over HTTP and WebSocket:

  POST  /simulate          → Enqueues a new simulation job and returns job_id
  POST  /simulate/refine   → AI refines an existing model
  POST  /simulate/update   → Hot-patches a parameter and re-runs (slider tuning)
  POST  /simulate/diagnose → AI explains a simulation error and suggests a fix
  GET   /simulate/{job_id} → Polls job status / result (REST fallback)
  WS    /ws/{job_id}       → Streams real-time simulation result to the browser

  POST  /license/validate  → Validates a Gumroad license key; returns tier
  GET   /license/portal    → Returns the Gumroad subscription-management URL

  GET   /blocks            → Returns the full Block Registry (drives UI palette)
  GET   /health            → Liveness probe

Design notes
------------
• The FastAPI app never calls Scilab directly; it only enqueues tasks.
• WebSocket clients subscribe to a Redis pub/sub channel named "job:<job_id>"
  so workers can push results without polling.
• CORS is intentionally permissive for development; tighten in production via
  the ALLOWED_ORIGINS environment variable.
• When a valid ``X-License-Key`` header is present on AI endpoints the backend
  uses CLOUD_OPENAI_API_KEY (the owner's key) instead of the local
  OPENAI_API_KEY, enabling the Pro cloud-AI tier.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.ai_engine import SimulationArchitect
from backend.block_registry import BLOCK_REGISTRY
from backend.license import (
    GUMROAD_MANAGE_URL,
    GUMROAD_PURCHASE_URL,
    cloud_openai_key,
    validate_license,
)
from backend.models import SimulationModel, SimulationResult
from backend.worker import celery_app, run_simulation
from backend.zcos_compiler import GraphValidationError, compile_to_zcos

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="System Link API",
    version="1.0.0",
    description=(
        "AI-native control-systems simulation platform. "
        "Professional-grade simulation, powered by AI."
    ),
)

_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-License-Key"],
)

# ---------------------------------------------------------------------------
# Redis client (async, for WebSocket pub/sub + license cache)
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_redis: Optional[aioredis.Redis] = None  # type: ignore[type-arg]


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Dependency: SimulationArchitect
# ---------------------------------------------------------------------------

_architect_cache: Dict[Optional[str], SimulationArchitect] = {}


def _get_architect(api_key: Optional[str] = None) -> SimulationArchitect:
    """
    Return a SimulationArchitect for the given *api_key*.

    Two singletons are maintained:
      • ``None``  — uses the default env-var OPENAI_API_KEY (free/self-hosted)
      • cloud key — uses CLOUD_OPENAI_API_KEY (Pro subscribers)

    This avoids re-instantiating the client on every request.
    """
    if api_key not in _architect_cache:
        import openai

        client = openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        _architect_cache[api_key] = SimulationArchitect(client=client)
    return _architect_cache[api_key]


async def _resolve_architect(
    x_license_key: Optional[str] = None,
) -> SimulationArchitect:
    """
    Resolve which SimulationArchitect to use based on the license key header.

    If the header contains a valid Gumroad license key and the cloud API key
    is configured, the Pro architect (using CLOUD_OPENAI_API_KEY) is returned.
    Otherwise the free/self-hosted architect (OPENAI_API_KEY) is used.
    """
    if x_license_key:
        redis = await get_redis()
        is_pro = await validate_license(x_license_key, redis)
        cloud_key = cloud_openai_key()
        if is_pro and cloud_key:
            log.debug("Serving request with cloud AI (Pro tier).")
            return _get_architect(cloud_key)
    return _get_architect(None)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str


class RefineRequest(BaseModel):
    model: SimulationModel
    instruction: str


class UpdateParameterRequest(BaseModel):
    model: SimulationModel
    block_id: str
    parameter: str
    value: float


class JobResponse(BaseModel):
    job_id: str
    status: str = "queued"
    message: Optional[str] = None


class DiagnoseRequest(BaseModel):
    model: SimulationModel
    error: str


class DiagnoseResponse(BaseModel):
    diagnosis: str
    suggestion: str


class LicenseValidateRequest(BaseModel):
    license_key: str


class LicenseValidateResponse(BaseModel):
    valid: bool
    tier: str  # "pro" | "free"
    message: str


class LicensePortalResponse(BaseModel):
    manage_url: str
    purchase_url: str


# ---------------------------------------------------------------------------
# Helper: semantic IR hash
# ---------------------------------------------------------------------------


def _ir_hash(model: SimulationModel) -> str:
    """
    Return a stable SHA-256 hash of the simulation-relevant IR fields.

    Excludes volatile fields that do not affect physics:
      • ``model.id``       — top-level UUID changes on every AI generation
      • ``model.metadata`` — AI commentary (intent, explanation, raw_prompt …)
      • ``block.ports``    — populated by the compiler, never set by the AI

    The result is used as the primary Redis cache key so that two requests
    for semantically identical models (e.g. slider tweaks that happen to
    land on the same value) share a cached result.
    """
    canonical = model.model_dump(
        exclude={"id": True, "metadata": True, "blocks": {"__all__": {"ports": True}}}
    )
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Helper: model diff logging (used by the refine route)
# ---------------------------------------------------------------------------


def _log_model_diff(old: SimulationModel, new: SimulationModel) -> None:
    """
    Emit a structured INFO log summarising what changed between two models.

    Compared dimensions:
      • Blocks added / removed (identified by id)
      • Parameter values that changed on retained blocks
      • Connection count delta
    """
    old_map = {b.id: b for b in old.blocks}
    new_map = {b.id: b for b in new.blocks}

    added = [
        f"{b.type.value}({b.id[:8]}…)"
        for b in new.blocks
        if b.id not in old_map
    ]
    removed = [
        f"{b.type.value}({b.id[:8]}…)"
        for b in old.blocks
        if b.id not in new_map
    ]

    param_changes: list[str] = []
    for b in new.blocks:
        if b.id in old_map:
            old_b = old_map[b.id]
            for k, v in b.parameters.items():
                old_v = old_b.parameters.get(k)
                if old_v is not None and old_v != v:
                    param_changes.append(
                        f"{b.type.value}.{k}: {old_v:.4g} → {v:.4g}"
                    )

    conn_old = {
        (c.source_block, c.source_port, c.target_block, c.target_port)
        for c in old.connections
    }
    conn_new = {
        (c.source_block, c.source_port, c.target_block, c.target_port)
        for c in new.connections
    }

    log.info(
        "Refine diff — blocks: +[%s] -[%s]; params: [%s]; connections: +%d -%d",
        ", ".join(added) if added else "none",
        ", ".join(removed) if removed else "none",
        ", ".join(param_changes) if param_changes else "none",
        len(conn_new - conn_old),
        len(conn_old - conn_new),
    )


# ---------------------------------------------------------------------------
# Helper: enqueue a simulation
# ---------------------------------------------------------------------------


def _enqueue(model: SimulationModel, queue: str = "flux_high") -> str:
    """Compile model → ZCOS, enqueue Celery task on *queue*, return job_id."""
    try:
        zcos_bytes = compile_to_zcos(model)
    except GraphValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Unexpected compilation error")
        raise HTTPException(
            status_code=500,
            detail="Internal compilation error. Please try again.",
        ) from exc

    ir_hash = _ir_hash(model)
    job_id = str(uuid.uuid4())
    run_simulation.apply_async(
        args=[job_id, zcos_bytes.hex(), ir_hash],
        task_id=job_id,
        queue=queue,
    )
    log.debug("Enqueued job %s on queue '%s' (ir_hash=%s…).", job_id, queue, ir_hash[:16])
    return job_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "system-link-api", "version": "1.0.0"}


@app.get("/blocks")
async def list_blocks() -> Dict[str, Any]:
    """Return the full Block Registry so the UI can render the block palette."""
    return {
        name: {
            "canonical_name": spec.canonical_name,
            "xcos_name": spec.xcos_name,
            "n_inputs": spec.n_inputs,
            "n_outputs": spec.n_outputs,
            "description": spec.description,
            "params": [
                {
                    "name": p.name,
                    "label": p.label,
                    "default": p.default,
                    "min": p.min_value,
                    "max": p.max_value,
                    "tunable": p.tunable,
                    "unit": p.unit,
                }
                for p in spec.params
            ],
        }
        for name, spec in BLOCK_REGISTRY.items()
    }


# ---------------------------------------------------------------------------
# License endpoints
# ---------------------------------------------------------------------------


@app.post("/license/validate", response_model=LicenseValidateResponse)
async def license_validate(req: LicenseValidateRequest) -> LicenseValidateResponse:
    """
    Validate a Gumroad license key.

    Returns ``{"valid": true, "tier": "pro"}`` for active subscriptions, or
    ``{"valid": false, "tier": "free"}`` for invalid / expired keys.

    Results are cached in Redis for 24 hours to avoid hitting the Gumroad
    API on every keystroke.
    """
    redis = await get_redis()
    is_valid = await validate_license(req.license_key, redis)

    if is_valid:
        return LicenseValidateResponse(
            valid=True,
            tier="pro",
            message="Pro license activated. Thank you for subscribing!",
        )
    return LicenseValidateResponse(
        valid=False,
        tier="free",
        message=(
            "License key not recognised or subscription is no longer active. "
            "Please check your key and try again."
        ),
    )


@app.get("/license/portal", response_model=LicensePortalResponse)
async def license_portal() -> LicensePortalResponse:
    """
    Return URLs for Gumroad subscription management.

    ``manage_url``   — Gumroad's "My Purchases" page where users can cancel.
    ``purchase_url`` — Product page to start a new subscription.
    """
    return LicensePortalResponse(
        manage_url=GUMROAD_MANAGE_URL,
        purchase_url=GUMROAD_PURCHASE_URL,
    )


# ---------------------------------------------------------------------------
# Simulation routes
# ---------------------------------------------------------------------------


@app.post("/simulate", response_model=JobResponse)
async def simulate(
    req: GenerateRequest,
    x_license_key: Optional[str] = Header(default=None),
) -> JobResponse:
    """
    Generate a SimulationModel from a natural-language prompt, compile it,
    and enqueue the simulation job.

    If a valid ``X-License-Key`` header is present and ``CLOUD_OPENAI_API_KEY``
    is configured, the cloud (Pro) AI engine is used; otherwise the self-hosted
    engine (``OPENAI_API_KEY``) is used.
    """
    architect = await _resolve_architect(x_license_key)
    try:
        model = architect.generate(req.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = _enqueue(model)
    return JobResponse(
        job_id=job_id,
        status="queued",
        message=model.metadata.intent if model.metadata else None,
    )


@app.post("/simulate/refine", response_model=JobResponse)
async def refine(
    req: RefineRequest,
    x_license_key: Optional[str] = Header(default=None),
) -> JobResponse:
    """
    Modify an existing model via a natural-language instruction and re-run.
    Logs a structured diff so developers can see exactly what the AI changed.
    """
    architect = await _resolve_architect(x_license_key)
    try:
        updated_model = architect.refine(req.model, req.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _log_model_diff(req.model, updated_model)
    job_id = _enqueue(updated_model)
    return JobResponse(job_id=job_id, status="queued")


@app.post("/simulate/diagnose", response_model=DiagnoseResponse)
async def diagnose_simulation(
    req: DiagnoseRequest,
    x_license_key: Optional[str] = Header(default=None),
) -> DiagnoseResponse:
    """
    Ask the AI to diagnose a simulation error and suggest a specific fix.

    Accepts the model that failed and the error message shown to the user.
    Returns a plain-English ``diagnosis`` and an actionable ``suggestion``.
    Falls back gracefully if the LLM is unavailable.
    """
    architect = await _resolve_architect(x_license_key)
    result = architect.diagnose(req.model, req.error)
    return DiagnoseResponse(**result)


@app.post("/simulate/update", response_model=JobResponse)
async def update_parameter(req: UpdateParameterRequest) -> JobResponse:
    """
    Hot-patch a single parameter value and immediately re-run.
    This is the "slider tuning" endpoint—designed for <200 ms round-trips.
    """
    # Find the target block and update in-place
    target = next((b for b in req.model.blocks if b.id == req.block_id), None)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Block '{req.block_id}' not found in the model.",
        )

    # Pydantic models are immutable; rebuild with the updated parameter
    updated_params = {**target.parameters, req.parameter: req.value}
    updated_block = target.model_copy(update={"parameters": updated_params})
    updated_blocks = [
        updated_block if b.id == req.block_id else b
        for b in req.model.blocks
    ]
    updated_model = req.model.model_copy(update={"blocks": updated_blocks})

    # Slider updates are low-priority; high-priority queue is for new/refine jobs
    job_id = _enqueue(updated_model, queue="flux_low")
    return JobResponse(job_id=job_id, status="queued")


@app.get("/simulate/{job_id}", response_model=SimulationResult)
async def get_result(job_id: str) -> SimulationResult:
    """Poll simulation result (REST fallback; prefer WebSocket for live UX)."""
    task = celery_app.AsyncResult(job_id)

    if task.state == "PENDING":
        return SimulationResult(job_id=job_id, status="running")
    if task.state == "FAILURE":
        return SimulationResult(
            job_id=job_id,
            status="error",
            error_message="The simulation worker encountered an unexpected failure.",
        )
    if task.state == "SUCCESS":
        return SimulationResult(**task.result)

    return SimulationResult(job_id=job_id, status=task.state.lower())


# ---------------------------------------------------------------------------
# WebSocket — real-time result streaming
# ---------------------------------------------------------------------------

_POLL_INTERVAL_S = 0.25
_WS_TIMEOUT_S = 120


@app.websocket("/ws/{job_id}")
async def websocket_result(websocket: WebSocket, job_id: str) -> None:
    """
    Stream simulation progress and result to the browser.

    Protocol
    --------
    Server → Client messages (JSON):
      {"status": "running"}
      {"status": "success", "time": [...], "signals": {...}, ...}
      {"status": "error", "error_message": "..."}
    """
    await websocket.accept()
    deadline = asyncio.get_event_loop().time() + _WS_TIMEOUT_S

    try:
        while asyncio.get_event_loop().time() < deadline:
            task = celery_app.AsyncResult(job_id)

            if task.state in ("SUCCESS", "FAILURE"):
                if task.state == "SUCCESS":
                    result = SimulationResult(**task.result)
                else:
                    result = SimulationResult(
                        job_id=job_id,
                        status="error",
                        error_message="Simulation worker failed unexpectedly.",
                    )
                await websocket.send_text(result.model_dump_json())
                break

            await websocket.send_text(
                json.dumps({"status": "running", "job_id": job_id})
            )
            await asyncio.sleep(_POLL_INTERVAL_S)
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "status": "error",
                        "error_message": "Timed out waiting for simulation result.",
                    }
                )
            )
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected for job %s.", job_id)
    finally:
        await websocket.close()
