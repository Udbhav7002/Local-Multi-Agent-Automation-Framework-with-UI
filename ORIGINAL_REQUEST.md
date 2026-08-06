# Original User Request

## Initial Request — 2026-08-03T18:10:58Z

Execute a comprehensive 3-Phase Architectural Remediation across the Local Multi-Agent Automation Framework to eliminate LIFO prompt truncation memory loss, race conditions in GUI automation, blocking CLI loops, O(N) disk I/O bottlenecks in skill retrieval, API job tracking gaps, and blind step retries.

Working directory: /Users/sanagariudbhav/Udbhav/Projects/Local-Multi-Agent-Automation-Framework
Integrity mode: development

## Requirements

### R1. Core Reliability & Concurrency Hardening (Phase 1)
- Fix the LIFO prompt truncation bug in `PlanningContext._fit_to_budget_sync` so that when character budget is exceeded, oldest conversation history and oldest error feedback are dropped first, always preserving `original_task` and the most recent error feedback.
- Implement an async `GUI_LOCK` (`asyncio.Lock()`) in `GUIExecutor`/`ExecutorDispatcher` so mouse and keyboard actions are serialized across parallel tasks while CLI and Browser tasks remain fully concurrent.
- Replace blocking `Prompt.ask()` console input calls in `main.py` with non-blocking async input reading so the asyncio event loop remains responsive.

### R2. Memory Optimization & Vision Cleanup (Phase 2)
- Refactor `SkillLibrary` to use an in-memory dictionary cache on startup for O(1) lookups and semantic matching for deduplication so similar task descriptions share the same skill file.
- Completely remove the obsolete C++ `vision_ext/` directory and references in `ui_parser.py`, relying 100% on Python OpenCV/pytesseract OCR fallback.

### R3. Production API Tracking & Self-Correction Loop (Phase 3)
- Upgrade `api.py` to generate UUID job IDs, store job states (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `result`, `steps_executed`) in a lightweight SQLite database (`jobs.db`), and expose a `/status/{job_id}` GET endpoint.
- Refactor `StepRunner` step retries to invoke an interactive fast-path correction loop that returns error/vision feedback to the Worker LLM to adjust `ActionStep` payload before re-attempting.

## Verification Resources
- Python syntax verifier: `python3 -m py_compile <file>`
- Unit test runner: `pytest tests/`

## Acceptance Criteria

### Automated Test Verification
- [ ] Every modified Python file passes syntax compilation without errors (`python3 -m py_compile <modified_file>`).
- [ ] Automated `pytest` unit/integration tests are written for each phase (`test_planning_context_truncation.py`, `test_gui_concurrency.py`, `test_skill_library_cache.py`, `test_api_job_tracking.py`).
- [ ] 100% of existing and new automated tests in `tests/` pass when running `pytest tests/`.
- [ ] No regression or breaking changes to existing public protocol contracts (`StepRunner`, `Orchestrator`, `ExecutorDispatcher`).
