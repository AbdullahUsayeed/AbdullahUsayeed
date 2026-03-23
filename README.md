## Introduction

Hello! I'm an **Embedded Systems Developer** focused on **Edge AI and Industrial IoT**.

> **⚡ Project Flux** — AI-native control systems simulation platform — is scaffolded in this repo. See the [Project Flux](#-project-flux--ai-native-control-systems-simulation) section below for architecture, quick-start, and docs.

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

## ⚡ Project Flux — AI-Native Control Systems Simulation

> **"Simulink-grade simulation, in the browser, powered by natural language."**

Project Flux is a premium, open-core simulation platform that makes professional-grade control systems simulation accessible to everyone—no $2,000 license, no 40-hour learning curve.

### Architecture Overview

```
User (NL Prompt)
      │
      ▼
 PromptBar (React)
      │  POST /api/simulate
      ▼
 FastAPI Backend
      │  OpenAI / local LLM
      ▼
 SimulationArchitect  ←─  "Design a PID controller…"
      │  Produces SimulationModel (Pydantic V2 IR)
      ▼
 GraphValidator  ←─  Checks topology (no dangling ports, etc.)
      │
      ▼
 ZCOSCompiler  ←─  JSON → lxml tree → gzip .zcos
      │
      ▼
 Celery Task  →  Redis Queue
      │
      ▼
 Warm Scilab Worker  ←─  scilab-cli (headless, persistent)
      │  Runs simulation, writes CSV
      ▼
 SimulationResult  →  WebSocket  →  React UI (Recharts graph)
```

### Key Files

| File | Purpose |
|------|---------|
| `backend/models.py` | Pydantic V2 IR — `SimulationModel`, `BlockDefinition`, `Connection`, `AIMetadata` |
| `backend/block_registry.py` | Single source of truth for all Xcos block types & parameters |
| `backend/zcos_compiler.py` | Validate → Instantiate ports → Build lxml XML → gzip |
| `backend/ai_engine.py` | `SimulationArchitect` — LLM-agnostic NL→IR engine |
| `backend/worker.py` | Celery + Warm Scilab Pool |
| `backend/main.py` | FastAPI: `/simulate`, `/simulate/refine`, `/simulate/update`, `/ws/{job_id}` |
| `frontend/src/` | React + React Flow + Recharts + Zustand |
| `docker/Dockerfile.backend` | python:3.11-slim + scilab-cli (no GUI) |
| `docker-compose.yml` | backend + worker (×4) + frontend + redis |

### Quick Start

```bash
# 1. Configure
cp .env.example .env
# Add your OPENAI_API_KEY

# 2. Launch
docker compose up --build

# 3. Open
open http://localhost:3000

# Try: "Second-order system with ωn=10 rad/s and ζ=0.7, unit step input"
```

### Scale Workers

```bash
docker compose up --scale worker=10  # 10 simultaneous simulations
```

### Switch LLM (no code change)

```bash
OPENAI_BASE_URL=http://localhost:11434/v1 LLM_MODEL=llama3 docker compose up
```
