"""
Project Flux — FastAPI Application
====================================
Exposes the simulation pipeline over HTTP and WebSocket:

  POST  /simulate          → Enqueues a new simulation job and returns job_id
  POST  /simulate/refine   → AI refines an existing model
  POST  /simulate/update   → Hot-patches a parameter and re-runs (slider tuning)
  GET   /simulate/{job_id} → Polls job status / result (REST fallback)
  WS    /ws/{job_id}       → Streams real-time simulation result to the browser

  GET   /blocks            → Returns the full Block Registry (drives UI palette)
  GET   /health            → Liveness probe

Design notes
------------
• The FastAPI app never calls Scilab directly; it only enqueues tasks.
• WebSocket clients subscribe to a Redis pub/sub channel named "job:<job_id>"
  so workers can push results without polling.
• CORS is intentionally permissive for development; tighten in production via
  the ALLOWED_ORIGINS environment variable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.ai_engine import SimulationArchitect
from backend.block_registry import BLOCK_REGISTRY
from backend.models import SimulationModel, SimulationResult
from backend.worker import celery_app, run_simulation
from backend.zcos_compiler import GraphValidationError, compile_to_zcos

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Project Flux API",
    version="1.0.0",
    description=(
        "AI-native simulation platform. "
        "Simulink-grade control-systems simulation, powered by Scilab Xcos."
    ),
)

_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Redis client (async, for WebSocket pub/sub)
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_redis: Optional[aioredis.Redis] = None  # type: ignore[type-arg]


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Dependency: SimulationArchitect (singleton)
# ---------------------------------------------------------------------------

_architect: Optional[SimulationArchitect] = None


def get_architect() -> SimulationArchitect:
    global _architect
    if _architect is None:
        _architect = SimulationArchitect()
    return _architect


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


# ---------------------------------------------------------------------------
# Helper: enqueue a simulation
# ---------------------------------------------------------------------------


def _enqueue(model: SimulationModel) -> str:
    """Compile model → ZCOS, enqueue Celery task, return job_id."""
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

    job_id = str(uuid.uuid4())
    run_simulation.apply_async(
        args=[job_id, zcos_bytes.hex()],
        task_id=job_id,
    )
    return job_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "project-flux-api"}


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


@app.post("/simulate", response_model=JobResponse)
async def simulate(req: GenerateRequest) -> JobResponse:
    """
    Generate a SimulationModel from a natural-language prompt, compile it,
    and enqueue the simulation job.
    """
    architect = get_architect()
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
async def refine(req: RefineRequest) -> JobResponse:
    """
    Modify an existing model via a natural-language instruction and re-run.
    """
    architect = get_architect()
    try:
        updated_model = architect.refine(req.model, req.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = _enqueue(updated_model)
    return JobResponse(job_id=job_id, status="queued")


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

    job_id = _enqueue(updated_model)
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
