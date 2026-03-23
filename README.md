## Introduction

Hello! I'm an **Embedded Systems Developer** focused on **Edge AI and Industrial IoT**.

> **⚡ System Link** — AI-native control systems simulation platform — is scaffolded in this repo. See the [System Link](#-system-link--ai-native-control-systems-simulation) section below for architecture, quick-start, and docs.

I design and build **hardware–software integrated systems**, working across the full development stack: **PCB design, firmware development, embedded networking, and edge machine learning**. My work centers around **distributed sensor systems, intelligent automation, and industrial monitoring solutions**.

---

## Tech Stack

**PCB Design:**
Altium Designer, KiCad

**CAD / Mechanical:**
FreeCAD

**Programming:**
C, C++, Python (Data Science & Backend), Rust *(learning)*, Java, HTML, CSS

**Embedded & Development Tools:**
FreeRTOS, STM32CubeIDE, PlatformIO, Docker, Arduino IDE

**Edge AI / Machine Learning:**
TensorFlow Lite for Microcontrollers, Edge Impulse

---

## Personal Lab & Prototyping

I maintain a **personal electronics lab** for rapid prototyping, testing, and experimentation.

**Instrumentation**

* Analog Discovery 2 (oscilloscope, waveform generator, logic analyzer)
* Multimeter for electrical measurement and debugging

**Prototyping Tools**

* LPKF PCB prototyper (rapid PCB fabrication up to 4-layer boards)
* Bambu Lab 3D printer for enclosure and mechanical prototyping

---

## Current Project

**Industrial HVAC Intelligence**

Developing a **decentralized LoRaWAN sensor network using STM32** for HVAC system monitoring.

Key functionality:

* Distributed sensor nodes
* Real-time calculation of **superheat and subcooling**
* Wireless telemetry via LoRaWAN
* Data transmission to a backend server for monitoring and analytics

Goal: enable **predictive maintenance and intelligent HVAC diagnostics**.

---

## Selected Projects

**STM32 No-Internet Game**
Standalone embedded game built on the STM32 Bluepill.

**IR-Based Parking Sensor**
Distance sensing system using IR modules and STM32 Bluepill.

**Class-AB Audio Amplifier**
Analog amplifier design and testing.

**Solar Power Inverter**
Designed a power inverter converting **solar DC to grid-compatible AC**.

**Personal Portfolio Website**
Developed a personal website using HTML and CSS.

**STM32CubeMX Automation**
Integrated an LLM with Python to automate configuration workflows in STM32CubeMX.

**ESP32-CAM AI Object Detection**
Used ESP32-CAM with ROS2 and Gazebo for object detection experiments.

**Embedded Lab Experiments**
Various STM32-based experiments and embedded system prototypes documented in my portfolio.

---

## Future Goals

My goal is to contribute to **industrial automation, embedded systems, and Edge AI technologies** in the technology sector of Germany.

I am particularly interested in working on **advanced embedded platforms, intelligent sensor networks, and industrial infrastructure systems**.

---

## ⚡ System Link — AI-Native Control Systems Simulation

> **"Professional-grade simulation. In the browser. Powered by natural language."**

**Proudly built by [Usayeed](https://usayeed.com)**

System Link is a premium simulation platform that makes professional-grade control systems simulation accessible to everyone — no $2,000 licence, no 40-hour learning curve.

### Pricing

| Tier | Price | AI Engine | How to get it |
|------|-------|-----------|---------------|
| **Free** | $0 | Your own OpenAI / local LLM key | Download & self-host |
| **Pro** | $14.99 / month | Cloud AI (no key needed) | [Subscribe on Gumroad](https://usayeed.gumroad.com) |

### Architecture

```
User (NL Prompt)
      │
      ▼
 PromptBar (React)
      │  POST /api/simulate  [X-License-Key header if Pro]
      ▼
 FastAPI Backend
      │  ┌─ Free: user's OPENAI_API_KEY
      │  └─ Pro:  CLOUD_OPENAI_API_KEY (validated via Gumroad)
      ▼
 SimulationArchitect  ←─  "Design a PID controller…"
      │  Produces SimulationModel (Pydantic V2 IR)
      ├─ ModelAutoFixer  ← deterministic post-AI correction
      ▼
 GraphValidator  ←─  Checks topology
      │
      ▼
 ZCOSCompiler  ←─  JSON → lxml tree → gzip .zcos
      │
      ▼
 Celery Task  →  Redis Queue
      │
      ▼
 Warm Simulation Worker
      │  Runs simulation, writes CSV
      ▼
 SimulationResult  →  WebSocket  →  React UI (Recharts graph)
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/models.py` | Pydantic V2 IR — `SimulationModel`, `BlockDefinition`, `Connection`, `AIMetadata` |
| `backend/block_registry.py` | Single source of truth for all block types & parameters |
| `backend/zcos_compiler.py` | Validate → Instantiate ports → Build lxml XML → gzip |
| `backend/ai_engine.py` | `SimulationArchitect` — LLM-agnostic NL→IR engine |
| `backend/model_fixer.py` | `ModelAutoFixer` — deterministic post-AI correction layer |
| `backend/license.py` | Gumroad license validation (Redis-cached, 24 h TTL) |
| `backend/worker.py` | Celery + Warm Simulation Pool |
| `backend/main.py` | FastAPI: `/simulate`, `/license/validate`, `/ws/{job_id}`, … |
| `frontend/src/` | React + React Flow + Recharts + Zustand |
| `docker/Dockerfile.backend` | python:3.11-slim + scilab-cli (no GUI) |
| `docker-compose.yml` | backend + worker (×4) + frontend + redis |

---

### Free Tier — Self-Hosted Install

**Prerequisites:** Docker Desktop ([download](https://docs.docker.com/get-docker/))

#### Linux / macOS

```bash
chmod +x install.sh && ./install.sh
```

#### Windows

Double-click `install.bat`.

#### Manual

```bash
# 1. Configure
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 2. Launch
docker compose up --build

# 3. Open
open http://localhost:3000
```

---

### Pro Tier — Cloud AI Subscription

1. Subscribe at **[usayeed.gumroad.com](https://usayeed.gumroad.com)** ($14.99/month)
2. Gumroad will e-mail you a unique license key
3. Open System Link → click the **⚙ Settings** icon (top-right)
4. Paste your license key and click **Activate**
5. The **PRO** badge appears — cloud AI is now active

To cancel: Settings → **Manage / Cancel Subscription** → Gumroad subscription page.

---

### Scale Workers

```bash
docker compose up --scale worker=10  # 10 simultaneous simulations
```

### Switch LLM (no code change)

```bash
OPENAI_BASE_URL=http://localhost:11434/v1 LLM_MODEL=llama3 docker compose up
```

---

*Proudly built by [Usayeed](https://usayeed.com)*
