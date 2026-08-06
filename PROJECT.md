# Project: Local Multi-Agent Automation Framework 3-Phase Architectural Remediation

## Architecture
- `core/planning_context.py`: `PlanningContext` budget truncation management.
- `core/executor/gui_executor.py` & `core/executor/dispatcher.py`: GUI execution concurrency and locking (`GUI_LOCK`).
- `main.py`: Console user interaction loop.
- `core/skill_library.py`: Skill indexing, caching, and semantic deduplication.
- `core/ui_parser.py`: OCR and UI element detection (removing C++ `vision_ext/` dependency).
- `api.py`: FastAPI server, SQLite job database (`jobs.db`), and status tracking endpoint (`/status/{job_id}`).
- `core/step_runner.py`: Execution engine and fast-path self-correction loop.

## Feature Inventory
Every feature from the Survey phase must appear here with its assigned milestone. No feature may be left unassigned.
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | PlanningContext FIFO Truncation | Fix LIFO truncation bug in `PlanningContext._fit_to_budget_sync` to preserve `original_task` and newest `system_feedback` while dropping oldest entries first | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Async GUI Lock | Add `GUI_LOCK = asyncio.Lock()` in `GUIExecutor`/`ExecutorDispatcher` to serialize GUI actions while keeping CLI/Browser concurrent | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Non-blocking Console Input | Replace `Prompt.ask()` in `main.py` with non-blocking async input reading using `asyncio.to_thread` | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Phase 1 Unit Tests | Create `test_planning_context_truncation.py` and `test_gui_concurrency.py` in `tests/` | M1 | ORIGINAL_REQUEST §Acceptance |
| 5 | Skill Library In-Memory Cache | Refactor `SkillLibrary` with startup dictionary cache for O(1) lookups | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Skill Semantic Deduplication | Implement semantic similarity matching in `SkillLibrary` so similar descriptions share skill files | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Vision Ext Removal | Delete `vision_ext/` C++ folder and remove C++ references in `ui_parser.py`, defaulting 100% to OpenCV/pytesseract | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Phase 2 Unit Tests | Create `test_skill_library_cache.py` in `tests/` | M2 | ORIGINAL_REQUEST §Acceptance |
| 9 | API UUID & SQLite Job DB | Upgrade `api.py` to generate UUID job IDs and track state (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `result`, `steps_executed`) in `jobs.db` | M3 | ORIGINAL_REQUEST §R3 |
| 10 | API Status Endpoint | Expose GET `/status/{job_id}` in `api.py` | M3 | ORIGINAL_REQUEST §R3 |
| 11 | Interactive Fast-Path Correction Loop | Refactor `StepRunner` step retries to send error/vision feedback to Worker LLM to adjust `ActionStep` payload before re-attempting | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Phase 3 Unit Tests | Create `test_api_job_tracking.py` in `tests/` | M3 | ORIGINAL_REQUEST §Acceptance |
| 13 | E2E Test Verification | Ensure 100% of existing and new tests pass in `pytest tests/` and all files pass `python3 -m py_compile` | E2E | ORIGINAL_REQUEST §Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Reliability & Concurrency Hardening | Fix PlanningContext truncation, add GUI_LOCK, non-blocking input in main.py, unit tests | none | DONE |
| M2 | Memory Optimization & Vision Cleanup | SkillLibrary cache & deduplication, remove vision_ext/ & C++ code in ui_parser.py, unit tests | M1 | IN_PROGRESS |
| M3 | Production API Tracking & Self-Correction Loop | SQLite job tracking DB in api.py, GET /status/{job_id}, StepRunner fast-path correction loop, unit tests | M2 | PLANNED |
| E2E | E2E Testing & Verification Track | Comprehensive E2E test suite validation, regression check, 100% pytest pass, py_compile check | M1, M2, M3 | PLANNED |

## Interface Contracts
### StepRunner ↔ ActionStep / Worker LLM
- `StepRunner` signature and step execution loop must maintain existing public entry points (`StepRunner.run_step`, `StepRunner.execute_plan`).
- Step retry mechanism must call fast-path correction loop when step fails, supplying error message and vision screenshot/OCR feedback to LLM prompt generator before re-attempting.

### ExecutorDispatcher ↔ GUIExecutor / CLIExecutor / BrowserExecutor
- `ExecutorDispatcher.dispatch(step)` must maintain signature.
- `GUIExecutor` must use `async with self._lock:` around mouse/keyboard execution blocks (`GUI_LOCK = asyncio.Lock()`).
- `CLIExecutor` and `BrowserExecutor` MUST NOT acquire `GUI_LOCK`.

### api.py ↔ SQLite jobs.db
- `jobs.db` schema: `id TEXT PRIMARY KEY`, `status TEXT`, `result TEXT`, `steps_executed INTEGER`, `created_at TIMESTAMP`, `updated_at TIMESTAMP`.
- Endpoint `GET /status/{job_id}` returns JSON `{ "job_id": id, "status": status, "result": result, "steps_executed": steps_executed }`.

## Code Layout
- Code root: `/Users/sanagariudbhav/Udbhav/Projects/Local-Multi-Agent-Automation-Framework/`
- Core modules: `core/planning_context.py`, `core/executor/gui_executor.py`, `core/executor/dispatcher.py`, `core/skill_library.py`, `core/ui_parser.py`, `core/step_runner.py`
- Main entry point: `main.py`
- API entry point: `api.py`
- Tests directory: `tests/`
