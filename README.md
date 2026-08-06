<div align="center">

# 🤖 Local Multi-Agent Automation Framework

*An autonomous, privacy-first, multi-agent OS automation engine powered by local LLMs (Ollama) with a rich terminal dashboard and asynchronous REST API.*

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_AI-orange.svg)](https://ollama.com/)
[![ChromaDB](https://img.shields.io/badge/Memory-ChromaDB-purple.svg)](https://www.trychroma.com/)
[![SQLite](https://img.shields.io/badge/Job_Tracker-SQLite-003B57.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-60%20Passed-brightgreen.svg)]()

</div>

---

## ⚡ Overview

Welcome to the **Local Multi-Agent Automation Framework**, a high-performance automation system designed to execute desktop tasks, terminal commands, web navigation, and UI interactions directly on your operating system—**100% locally and privately**.

No cloud APIs, no telemetry, and no data leaving your hardware. Powered by **Ollama**, it coordinates a collaborative **Agent Army** (`Manager`, `Worker`, and `Vision`) with semantic memory and self-correcting retry loops.

---

## ✨ What's New: 3-Phase Architectural Remediation

This release includes hardened production reliability across the entire stack:
1. **🚀 Zero-Friction Launchers (`./start.sh` & `./stop.sh`)**: Smart auto-detection of virtual environments, dependencies, and local Ollama server status.
2. **🧠 Fast-Path Worker Self-Correction**: When a step fails, the `StepRunner` feeds the error output and current UI state back to the Worker LLM to generate a corrected action instead of blindly retrying.
3. **📋 SQLite Job Tracking (`jobs.db`)**: Persistent asynchronous job queue with UUID tracking for background REST API execution (`POST /prompt` & `GET /status/{job_id}`).
4. **🔒 Async ChromaDB & Safe UI Parser**: Proper `__aenter__`/`__aexit__` async context management and defensive multi-monitor OCR resilience.

---

## 🚀 Quick Start (Easiest Way to Run)

We provide smart terminal scripts that handle virtual environments, dependency installation, and service management automatically.

### 1. Prerequisites
- **macOS / Linux / Windows** with Python 3.10+
- **[Ollama](https://ollama.com)** installed and running locally
- (Optional) **Tesseract OCR** for computer vision text extraction

### 2. Launching the Framework

```bash
# Clone and enter directory
git clone https://github.com/Udbhav7002/Local-Multi-Agent-Automation-Framework-with-UI.git
cd Local-Multi-Agent-Automation-Framework-with-UI

# Make launcher scripts executable
chmod +x start.sh stop.sh
```

#### **Option A: Interactive Terminal Dashboard (Recommended)**
```bash
./start.sh
```
*launches the rich interactive dashboard with live diagnostic indicators and slash command controls.*

#### **Option B: Asynchronous REST API Server (Foreground)**
```bash
./start.sh --api
```
*Starts the FastAPI server on `http://127.0.0.1:8000` with hot-reload enabled.*

#### **Option C: Background Daemon API Server**
```bash
./start.sh --bg
```
*Runs the API server in the background and writes process ID to `.api.pid`.*

#### **Stopping Services**
```bash
./stop.sh
```
*Gracefully terminates any running background API servers or orphaned instances.*

> **macOS Users:** You can also double-click **`Runner.command`** (Terminal UI) or **`Runner_API.command`** (API Server) directly in Finder!

---

## 🎮 Interactive Terminal UI & Slash Commands

When running `./start.sh`, you are greeted by an interactive dashboard showing real-time Ollama status, system architecture, active models, and quick-access commands.

### ⚡ Practical Slash Commands

| Command | Description | Example Usage |
| :--- | :--- | :--- |
| **`/help`** | Display interactive command guide and shortcuts | `/help` |
| **`/status`** | Live dashboard of Ollama ping, memory stats, and SQLite job counts | `/status` |
| **`/skills`** | List reusable learned skills cached in `SkillLibrary` | `/skills` |
| **`/jobs`** | View recent background API tasks stored in `jobs.db` | `/jobs` |
| **`/history`** | Show prompt and execution history for the current session | `/history` |
| **`/model`** | Hot-swap active models for `manager`, `worker`, or `vision` | `/model worker qwen2.5-coder:14b` |
| **`/voice`** | Dictate your task hands-free using microphone input | `/voice` |
| **`/clear`** | Clear terminal display and re-draw the status dashboard | `/clear` |
| **`/save`** | Persist session state and runtime configurations | `/save` |
| **`/quit`** | Cleanly exit the framework and shut down executors | `/quit` |

---

## 💡 Practical Real-World Tasks to Try

You can type natural language instructions directly into the prompt:

```text
agent ❯ Open Safari and search for Tokyo weather forecast
agent ❯ Take a screenshot and summarize visible text on screen
agent ❯ Open Terminal, check disk space, and report available GB
agent ❯ List top 5 running processes by CPU usage and explain
agent ❯ Write a Python script on Desktop that calculates Fibonacci numbers
```

---

## 🌐 Asynchronous REST API Reference

When running `./start.sh --api` or `./start.sh --bg`, the FastAPI service provides remote execution endpoints:

### **Authentication**
All endpoints require an API key header (default: `local-dev-key` or set via `AGENT_API_KEY`):
```http
X-API-Key: local-dev-key
```

### **Endpoints**

#### 1. Submit Automation Task
- **`POST /prompt`** (Returns `202 Accepted`)
- Requests execution in background via `sqlite3` job tracking.
```json
// Request Body
{
  "text": "Open Notes app and create a new note with today's date"
}

// Response
{
  "job_id": "c3a1b89d-4822-4a7b-94d1-5829104c8f3e",
  "status": "queued"
}
```

#### 2. Check Job Status
- **`GET /status/{job_id}`**
- Returns real-time execution progress from `jobs.db`.
```json
{
  "job_id": "c3a1b89d-4822-4a7b-94d1-5829104c8f3e",
  "status": "COMPLETED",
  "result": "Note created successfully.",
  "steps_executed": "[{\"action\": \"open_app\", ...}]",
  "created_at": "2026-08-04T14:25:00+00:00",
  "updated_at": "2026-08-04T14:25:12+00:00"
}
```

#### 3. Health Check
- **`GET /health`**
- Returns server readiness and configured local models.
```json
{
  "status": "healthy",
  "manager_model": "llama3:latest",
  "worker_model": "llama3:latest",
  "vision_model": "llava:latest"
}
```

---

## 🏗️ Architecture & The Agent Army

```
                     +---------------------------+
                     |   User Terminal / API     |
                     +-------------+-------------+
                                   |
                                   v
                     +---------------------------+
                     |       Orchestrator        |
                     +-------------+-------------+
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
  +------------------+   +------------------+   +------------------+
  |  Manager Agent   |   |   Worker Agent   |   |   Vision Agent   |
  |  (Task Planner)  |   |  (Step Executor) |   |  (OCR & Screen)  |
  +--------+---------+   +--------+---------+   +--------+---------+
           |                      |                      |
           +----------------------+----------------------+
                                  |
                                  v
         +-------------------------------------------------+
         | ChromaDB (Semantic Memory) + SQLite (Job Queue) |
         +-------------------------------------------------+
```

- **Manager (`TaskPlanner` & `TaskCritic`)**: Breaks high-level prompts into step-by-step execution plans and evaluates outcomes.
- **Worker (`TaskWorker` & `StepRunner`)**: Converts steps into precise OS commands (`CLI`, `GUI`, or `Browser`) and applies **LLM self-correction** if a command encounters an error.
- **Vision (`UIParser`)**: Captures screen states, performs Tesseract OCR text extraction, and verifies UI outcomes.
- **Memory Store**: Remembers successful plans in `ChromaDB` and caches reusable skills in `SkillLibrary` for instant fast-path execution.

---

## 🧪 Running Tests

The framework includes an automated pytest suite covering concurrency, memory truncation, job tracking, and safety gates:

```bash
./start.sh --check
# Or directly:
pytest tests/ -v
```

---

<div align="center">
Made with ❤️ by Udbhav7002 • 100% Privacy-First OS Automation
</div>