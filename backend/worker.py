"""
Project Flux — Celery Worker (Scilab Execution Engine)
=======================================================
Each Celery worker maintains a **persistent, warm** Scilab CLI process.
When a job arrives the worker:

  1. Writes the gzip-compressed .zcos to a temp file.
  2. Writes a small Scilab runner script (.sce).
  3. Pipes the runner into the already-running Scilab REPL via stdin.
  4. Reads stdout/stderr until the sentinel token "FLUX_DONE" appears.
  5. Parses the CSV result file written by the runner script.
  6. Returns a ``SimulationResult`` serialised as JSON.

The Warm Pool is achieved because the Scilab process is spawned once at
worker startup (``@worker_init.connect``) and reused for every subsequent job.
Idle workers fall back to spawning a fresh process if the warm instance dies.

Environment variables
---------------------
SCILAB_CMD          Path to the scilab-cli binary (default: "scilab-cli")
SCILAB_TIMEOUT_S    Per-simulation hard timeout in seconds (default: 60)
REDIS_URL           Celery broker URL (default: "redis://redis:6379/0")
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import subprocess
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from typing import Optional

import redis as _redis_sync
from celery import Celery
from celery.signals import worker_init, worker_shutdown

from backend.models import SimulationResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "flux_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker process
    task_acks_late=True,            # acknowledge only after completion
    task_default_queue="flux_high", # new/refine simulations go here by default
)

# ---------------------------------------------------------------------------
# Simulation result cache (Redis, synchronous)
# ---------------------------------------------------------------------------

_CACHE_TTL_S = 3600  # cache successful results for 1 hour
_CACHE_KEY_IR_PREFIX = "flux:sim:ir:"    # preferred: keyed by semantic IR hash
_CACHE_KEY_ZCOS_PREFIX = "flux:sim:zcos:" # fallback: keyed by ZCOS bytes hash

_sim_cache: Optional[_redis_sync.Redis] = None  # type: ignore[type-arg]


def _get_sim_cache() -> _redis_sync.Redis:  # type: ignore[type-arg]
    """Return a lazily-initialised synchronous Redis client used for caching."""
    global _sim_cache
    if _sim_cache is None:
        _sim_cache = _redis_sync.from_url(REDIS_URL, decode_responses=True)
    return _sim_cache


def _ir_cache_key(ir_hash: str) -> str:
    """Cache key derived from the semantic IR hash (preferred)."""
    return f"{_CACHE_KEY_IR_PREFIX}{ir_hash}"


def _zcos_cache_key(zcos_bytes_hex: str) -> str:
    """Cache key derived from the ZCOS payload hash (legacy fallback)."""
    digest = hashlib.sha256(zcos_bytes_hex.encode()).hexdigest()
    return f"{_CACHE_KEY_ZCOS_PREFIX}{digest}"

# ---------------------------------------------------------------------------
# Warm Scilab process (process-local singleton)
# ---------------------------------------------------------------------------

SCILAB_CMD = os.environ.get("SCILAB_CMD", "scilab-cli")
SCILAB_TIMEOUT_S = int(os.environ.get("SCILAB_TIMEOUT_S", "60"))

_warm_scilab: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
# Guards all reads and writes of _warm_scilab so that startup/teardown signal
# handlers and task execution cannot race even if the OS scheduler interrupts
# between the poll() check and the subsequent read/write.
_scilab_lock = threading.Lock()


def _spawn_scilab() -> subprocess.Popen:  # type: ignore[type-arg]
    """Launch a headless Scilab REPL and return the Popen handle."""
    proc = subprocess.Popen(
        [SCILAB_CMD, "-nw", "-nwni", "-noatomsautoload"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    # Drain the Scilab banner
    _drain_until(proc, "-->", timeout=30)
    log.info("Warm Scilab process started (PID=%s).", proc.pid)
    return proc


def _drain_until(proc: subprocess.Popen, sentinel: str, timeout: int = 60) -> str:  # type: ignore[type-arg]
    """Read lines from *proc* stdout until *sentinel* appears or timeout."""
    buf: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if not line:
            break
        buf.append(line)
        if sentinel in line:
            break
    return "".join(buf)


@worker_init.connect
def warm_start_scilab(**_kwargs: object) -> None:
    """Called once per worker process at startup."""
    global _warm_scilab
    try:
        proc = _spawn_scilab()
        with _scilab_lock:
            _warm_scilab = proc
    except Exception:
        log.warning("Could not pre-warm Scilab; will spawn per-job.", exc_info=True)


@worker_shutdown.connect
def teardown_scilab(**_kwargs: object) -> None:
    """Gracefully terminate the warm Scilab process on worker shutdown."""
    global _warm_scilab
    with _scilab_lock:
        if _warm_scilab and _warm_scilab.poll() is None:
            _warm_scilab.terminate()
        _warm_scilab = None


def _get_scilab() -> subprocess.Popen:  # type: ignore[type-arg]
    """Return the warm process, respawning if it has died."""
    global _warm_scilab
    with _scilab_lock:
        if _warm_scilab is None or _warm_scilab.poll() is not None:
            log.info("Warm Scilab process is dead; respawning.")
            _warm_scilab = _spawn_scilab()
        return _warm_scilab


# ---------------------------------------------------------------------------
# Runner script generator
# ---------------------------------------------------------------------------

_RUNNER_TEMPLATE = textwrap.dedent("""\
    // Auto-generated by Project Flux — do not edit
    importXcosDiagram("{zcos_path}");
    xcos_simulate(scs_m, 4);  // mode 4 = run headlessly
    t = ans.time;
    y = ans.y;
    csvWrite([t, y], "{csv_path}", " ");
    disp("FLUX_DONE");
""")


def _build_runner(zcos_path: str, csv_path: str) -> str:
    return _RUNNER_TEMPLATE.format(zcos_path=zcos_path, csv_path=csv_path)


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------


def _parse_csv(csv_path: str) -> tuple[list[float], dict[str, list[float]]]:
    """
    Parse the space-delimited CSV written by the Scilab runner.

    Returns (time_array, {channel_name: values}).
    """
    time_col: list[float] = []
    channel_cols: dict[str, list[float]] = {}

    with open(csv_path, newline="") as fh:
        reader = csv.reader(fh, delimiter=" ")
        for row in reader:
            vals = [float(v) for v in row if v.strip()]
            if not vals:
                continue
            time_col.append(vals[0])
            for idx, val in enumerate(vals[1:], start=1):
                key = f"channel_{idx}"
                channel_cols.setdefault(key, []).append(val)

    return time_col, channel_cols


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="flux.run_simulation", max_retries=1)
def run_simulation(self, job_id: str, zcos_bytes_hex: str, ir_hash: str = "") -> dict:  # type: ignore[override]
    """
    Execute a simulation given the hex-encoded gzip ZCOS bytes.

    Cache strategy
    --------------
    If *ir_hash* is provided (computed from the semantic IR before compilation),
    it is used as the cache key.  This gives semantic cache hits: two requests
    for the same model topology/parameters hit the cache even if the model's
    top-level UUID differs.  Falls back to hashing the ZCOS bytes for
    backwards-compatibility when *ir_hash* is empty.

    Returns a ``SimulationResult`` serialised as a dict (JSON-compatible).
    """
    start_ms = time.monotonic() * 1000

    # ── Cache lookup ──────────────────────────────────────────────────────
    key = _ir_cache_key(ir_hash) if ir_hash else _zcos_cache_key(zcos_bytes_hex)
    try:
        cached = _get_sim_cache().get(key)
        if cached is not None:
            log.info("Cache hit for job %s (key=%s…).", job_id, key[:24])
            result_dict: dict = json.loads(cached)
            result_dict["job_id"] = job_id
            return result_dict
    except Exception:  # noqa: BLE001
        log.warning("Cache lookup failed for job %s; proceeding without cache.", job_id, exc_info=True)

    with tempfile.TemporaryDirectory(prefix="flux_") as tmpdir:
        zcos_path = str(Path(tmpdir) / "model.zcos")
        csv_path = str(Path(tmpdir) / "result.csv")

        # Write the ZCOS file
        with open(zcos_path, "wb") as fh:
            fh.write(bytes.fromhex(zcos_bytes_hex))

        # Build runner script
        runner_script = _build_runner(zcos_path, csv_path)

        try:
            scilab = _get_scilab()
            assert scilab.stdin is not None
            scilab.stdin.write(runner_script + "\n")
            scilab.stdin.flush()
            output = _drain_until(scilab, "FLUX_DONE", timeout=SCILAB_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return SimulationResult(
                job_id=job_id,
                status="error",
                error_message=(
                    "The simulation exceeded the time limit. "
                    "Try reducing the final simulation time or simplifying your model."
                ),
            ).model_dump()
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, (SystemExit, KeyboardInterrupt)):
                raise
            log.exception("Scilab execution failed for job %s", job_id)
            return SimulationResult(
                job_id=job_id,
                status="error",
                error_message=(
                    "An unexpected error occurred during simulation. "
                    f"Internal detail (not shown to user): {exc!r}"
                ),
            ).model_dump()

        if "FLUX_DONE" not in output:
            # Extract a clean snippet from Scilab's output for internal logging
            log.error("Scilab did not signal completion for job %s:\n%s", job_id, output)
            # The Scilab process is in an unknown state; kill it so the next
            # job gets a fresh process rather than a corrupted REPL.
            global _warm_scilab
            with _scilab_lock:
                if _warm_scilab is not None and _warm_scilab.poll() is None:
                    log.warning("Killing stuck Scilab process (PID=%s).", _warm_scilab.pid)
                    try:
                        _warm_scilab.kill()
                    except OSError:
                        pass
                _warm_scilab = None
            return SimulationResult(
                job_id=job_id,
                status="error",
                error_message=(
                    "The simulation did not complete successfully. "
                    "There may be a numerical instability in your model. "
                    "Try reducing the gain or adding a low-pass filter."
                ),
            ).model_dump()

        # Parse results
        try:
            time_col, channels = _parse_csv(csv_path)
        except (FileNotFoundError, ValueError) as exc:
            log.warning("CSV parse failed for job %s: %s", job_id, exc)
            return SimulationResult(
                job_id=job_id,
                status="error",
                error_message=(
                    "The simulation ran but produced no output. "
                    "Make sure your SCOPE block is connected to a signal."
                ),
            ).model_dump()

        elapsed_ms = time.monotonic() * 1000 - start_ms
        result = SimulationResult(
            job_id=job_id,
            status="success",
            time=time_col,
            signals=channels,
            execution_time_ms=round(elapsed_ms, 2),
        )

        # ── Cache store ───────────────────────────────────────────────────
        try:
            _get_sim_cache().setex(key, _CACHE_TTL_S, result.model_dump_json())
            log.debug("Cached result for job %s (key=%s…).", job_id, key[:16])
        except Exception:  # noqa: BLE001
            log.warning("Failed to cache result for job %s.", job_id, exc_info=True)

        return result.model_dump()
