# Changelog — System Link

All notable changes to **System Link** are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-04-05

### Added
- **AI-native simulation pipeline** — describe any control system in plain English and receive a professional-grade simulation in seconds.
- **SimulationArchitect** — LLM-agnostic NL → IR engine (`backend/ai_engine.py`).
- **ModelAutoFixer** — deterministic post-AI correction layer (`backend/model_fixer.py`).
- **ZCOSCompiler** — Pydantic IR → lxml XML → gzip `.zcos` file (`backend/zcos_compiler.py`).
- **Block Registry** — single source of truth for all Xcos block types and parameters (`backend/block_registry.py`).
- **GraphValidator** — validates block topology before compilation.
- **Celery Warm Pool** — pre-warmed Scilab CLI workers for low-latency simulation (`backend/worker.py`).
- **Priority queues** — `flux_high` for new/refine jobs, `flux_low` for slider-tuning hot-patches.
- **WebSocket streaming** — real-time simulation result delivery to the React UI.
- **REST fallback** — `GET /simulate/{job_id}` for environments where WebSocket is unavailable.
- **`/simulate/refine`** — modify an existing model via a natural-language instruction.
- **`/simulate/diagnose`** — AI-powered diagnosis of simulation errors.
- **`/simulate/update`** — hot-patch a single parameter and immediately re-run (<200 ms round-trip).
- **Gumroad license validation** — Redis-cached (24 h TTL) Pro subscription gating (`backend/license.py`).
- **React + React Flow canvas** — interactive block diagram editor.
- **Recharts graph** — real-time simulation output visualisation with ghost-result overlay.
- **Parameter sidebar** — live tunable sliders for every registered block parameter.
- **Settings panel** — license key activation, LLM model selector, API key entry.
- **One-command install** — `install.sh` (Linux/macOS) and `install.bat` (Windows).
- **Docker Compose stack** — backend + 4 Celery workers + frontend (Nginx) + Redis.
- **Free tier** — self-hosted with your own OpenAI API key (or any OpenAI-compatible local LLM).
- **Pro tier** — $14.99/month via Gumroad; cloud AI key managed server-side.
- **GitHub Actions release workflow** — automated versioned zip archive on every `v*` tag.

---

[1.0.0]: https://github.com/AbdullahUsayeed/AbdullahUsayeed/releases/tag/v1.0.0
