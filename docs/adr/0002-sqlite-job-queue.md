# ADR 0002: SQLite + Asyncio Queue for Background Jobs

## Context
The API layer of the framework requires a robust way to accept incoming automation tasks (`/prompt`) and execute them asynchronously without blocking the HTTP response. The framework also needs to be resilient to unexpected crashes and able to resume in-flight work.

## Decision
We chose a combination of an embedded SQLite database (`jobs.db`) to persist job payloads and states, paired with an in-memory `asyncio.Queue` worker pool for execution, rather than a heavy distributed queue like Celery or Redis/RQ.

## Rationale
1. **Dependency Minimization**: The framework is designed to run locally on a user's machine. Requiring a separate Redis server or RabbitMQ broker adds massive friction to installation.
2. **Durability**: By writing the payload and state transitions to SQLite (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`), we achieve durability.
3. **Crash Recovery**: The FastAPI `lifespan` event reads `QUEUED` jobs from SQLite on startup and re-inserts them into the `asyncio.Queue`, ensuring dropped tasks are resumed.

## Consequences
- Single-node architecture only (which aligns with the "local OS automation" philosophy).
- Cannot scale to hundreds of concurrent job runners due to SQLite write locks and single-process Python limitations.
