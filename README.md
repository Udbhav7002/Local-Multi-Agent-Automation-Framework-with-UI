# Local Multi-Agent Automation Framework

A multi-agent OS automation system that runs entirely on your machine. Natural-language tasks are planned and executed locally — terminal commands, GUI interaction, screen reading, web navigation — using LLMs served by Ollama. No cloud APIs and no telemetry; nothing leaves your hardware.

## How it works

- **Manager** (`TaskPlanner`, `TaskCritic`) breaks a prompt into step-by-step plans and evaluates outcomes.
- **Worker** (`TaskWorker`, `StepRunner`) turns steps into CLI, GUI, or browser actions. When a step fails, it feeds the error output and current UI state back to the model to generate a corrected action instead of blindly retrying.
- **Vision** (`UIParser`) captures the screen, runs Tesseract OCR text extraction, and verifies UI outcomes.
- **Memory** — successful plans are stored in ChromaDB and reusable skills are cached in a `SkillLibrary` for fast-path execution.
- **Job tracking** — background API jobs are queued and tracked in SQLite (`jobs.db`).

## Requirements

- Python 3.10+ on macOS, Linux, or Windows
- [Ollama](https://ollama.com) installed and running locally
- Optional: Tesseract OCR for screen text extraction

Models are configured in `.env` (see `.env.example`). The defaults are `qwen3-coder:30b` for the manager, `qwen2.5-coder:14b` for the worker, and `qwen2.5vl:7b` for vision.

## Quick start

```bash
git clone https://github.com/Udbhav7002/Local-Multi-Agent-Automation-Framework-with-UI.git
cd Local-Multi-Agent-Automation-Framework-with-UI
chmod +x start.sh stop.sh
```

`start.sh` creates a virtualenv and installs dependencies on first run, then checks that Ollama is reachable.

```bash
./start.sh          # interactive terminal dashboard
./start.sh --api    # FastAPI server on http://127.0.0.1:8000 (foreground, hot reload)
./start.sh --bg     # API server in the background, PID written to .api.pid
./start.sh --check  # run the test suite and dependency checks
./stop.sh           # stop background API servers and stray processes
```

On macOS you can also double-click `Runner.command` (terminal UI) or `Runner_API.command` (API server) in Finder.

## Terminal dashboard

`./start.sh` opens an interactive dashboard with live Ollama status, active models, and job counts. Slash commands:

| Command | Description |
| :--- | :--- |
| `/help` | Command guide and shortcuts |
| `/status` | Ollama ping, memory stats, SQLite job counts |
| `/skills` | List reusable skills cached in the SkillLibrary |
| `/jobs` | View recent background API jobs from `jobs.db` |
| `/history` | Prompt and execution history for the session |
| `/model` | Hot-swap the model for `manager`, `worker`, or `vision` (e.g. `/model worker qwen2.5-coder:14b`) |
| `/voice` | Dictate a task using microphone input |
| `/clear` | Clear the display and redraw the dashboard |
| `/save` | Persist session state and runtime configuration |
| `/quit` | Exit cleanly and shut down executors |

## Example tasks

Type natural-language instructions at the prompt:

```text
agent ❯ Open Safari and search for Tokyo weather forecast
agent ❯ Take a screenshot and summarize visible text on screen
agent ❯ Open Terminal, check disk space, and report available GB
agent ❯ List top 5 running processes by CPU usage and explain
agent ❯ Write a Python script on Desktop that calculates Fibonacci numbers
```

## REST API

Start with `./start.sh --api` or `./start.sh --bg`. All endpoints require an `X-API-Key` header. Set `AGENT_API_KEY` before starting the server; if it is unset outside production, the server generates a random key and logs it at startup.

### POST /v1/prompt

Submit a task for background execution. Returns `202 Accepted`. Rate limited to 10 requests per minute.

```json
// Request
{ "text": "Open Notes app and create a new note with today's date" }

// Response
{ "job_id": "c3a1b89d-4822-4a7b-94d1-5829104c8f3e", "status": "queued" }
```

### GET /v1/status/{job_id}

Current progress and result of a job, read from `jobs.db`:

```json
{
  "job_id": "c3a1b89d-4822-4a7b-94d1-5829104c8f3e",
  "status": "COMPLETED",
  "result": "Note created successfully."
}
```

### POST /v1/jobs/{job_id}/cancel

Cancel a queued or running job.

### GET /health

Server readiness and the configured manager, worker, and vision models.

## Architecture

```text
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

## Tests

```bash
./start.sh --check
# or directly:
pytest tests/ -v
```

The suite covers concurrency, planning context truncation, job tracking, response parsing, the skill cache, and safety gates.

## License

MIT — see [LICENSE](LICENSE).
