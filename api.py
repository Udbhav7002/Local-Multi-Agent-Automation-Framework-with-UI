"""
Asynchronous API Layer for the Local Multi-Agent Automation Framework.
"""
import os
import asyncio
import uuid
import json
import datetime
import secrets
import aiosqlite
import sqlite3
from datetime import timezone
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional
from urllib.parse import urlparse
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Security, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi import Request
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import Counter, Histogram, generate_latest
import httpx

from core.factory import FrameworkBuilder
from core.config import config
from core.logger import setup_logger
from core.events import TaskStateChangedEvent
from core.circuit_breaker import CircuitBreakerOpenError
from core.logger import set_task_id

logger = setup_logger("API")

API_KEY = os.environ.get("AGENT_API_KEY")
if not API_KEY:
    if os.environ.get("ENV") == "production":
        logger.error("AGENT_API_KEY is not set. Must be set in production environment.")
        raise ValueError("AGENT_API_KEY is not set for production environment")
    else:
        # In development, generate a random key and log it
        API_KEY = secrets.token_urlsafe(32)
        logger.warning("No AGENT_API_KEY set. Generated development key: %s", API_KEY)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not secrets.compare_digest(api_key_header, API_KEY):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key_header

class PromptRequest(BaseModel):
    text: str
    webhook_url: Optional[str] = None

class ErrorCode(str, Enum):
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    INVALID_API_KEY = "INVALID_API_KEY"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

class ErrorResponse(BaseModel):
    error_code: ErrorCode
    message: str
    request_id: str
    details: Optional[dict] = None

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_JOBS_DB_PATH = os.path.join(_PROJECT_ROOT, "jobs.db")

class JobStore:
    def __init__(self, db_path=_JOBS_DB_PATH):
        self.db_path = db_path
        self._pool = None

    async def connect(self):
        self._pool = await aiosqlite.connect(self.db_path)
        self._pool.row_factory = aiosqlite.Row
        await self._pool.execute("PRAGMA journal_mode=WAL")
        await self._pool.execute("PRAGMA foreign_keys=ON")
        await self._pool.commit()
        
        # Run sync migrations in a thread during initialization
        import sqlite3
        from migrations.runner import run_migrations
        await asyncio.to_thread(run_migrations, self.db_path)

        # Create indices
        await self._pool.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        await self._pool.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
        await self._pool.commit()

    async def close(self):
        if self._pool:
            await self._pool.close()

    async def create_job(self, job_id: str, payload: str = "", webhook_url: str = None) -> None:
        now = datetime.datetime.now(timezone.utc).isoformat()
        webhook_json = json.dumps({"url": webhook_url}) if webhook_url else None
        # We store webhook_url in the payload column as JSON alongside the text, or we can just append it to text since we don't have a webhook column.
        # Since we just added 'payload' column in migration 2, let's use it for a JSON dict holding extra info.
        job_data = json.dumps({"text": payload, "webhook_url": webhook_url})
        await self._pool.execute(
            "INSERT INTO jobs (job_id, status, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "QUEUED", job_data, now, now)
        )
        await self._pool.commit()

    async def update_job(self, job_id: str, status: str, result: str = None, steps_executed: list = None) -> None:
        now = datetime.datetime.now(timezone.utc).isoformat()
        steps_str = json.dumps(steps_executed) if steps_executed is not None else None
        
        if result is not None and steps_executed is not None:
            await self._pool.execute(
                "UPDATE jobs SET status = ?, result = ?, steps_executed = ?, updated_at = ? WHERE job_id = ?",
                (status, result, steps_str, now, job_id)
            )
        elif result is not None:
            await self._pool.execute(
                "UPDATE jobs SET status = ?, result = ?, updated_at = ? WHERE job_id = ?",
                (status, result, now, job_id)
            )
        elif steps_executed is not None:
            await self._pool.execute(
                "UPDATE jobs SET status = ?, steps_executed = ?, updated_at = ? WHERE job_id = ?",
                (status, steps_str, now, job_id)
            )
        else:
            await self._pool.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status, now, job_id)
            )
        await self._pool.commit()

    async def get_job(self, job_id: str) -> dict | None:
        async with self._pool.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def get_queued_jobs(self) -> list[dict]:
        async with self._pool.execute("SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC") as cursor:
            return [dict(row) for row in await cursor.fetchall()]

# Metrics
REQUEST_COUNT = Counter('agent_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('agent_request_duration_seconds', 'Request latency')
JOB_DURATION = Histogram('agent_job_duration_seconds', 'Job execution time', ['status'])

# Global orchestrator instance
orchestrator = None
job_store = None
active_job_tasks = set()
job_queue = asyncio.Queue()
cancellation_tokens = {}
_JOB_SEMAPHORE = asyncio.Semaphore(3)

async def background_summarization_job():
    while True:
        try:
            # Run every hour (3600 seconds)
            await asyncio.sleep(3600)
            if orchestrator and orchestrator.memory:
                logger.info("Running background episodic memory summarization...")
                await orchestrator.memory.summarize_old_episodes(100)
                
            # Cleanup old screenshots
            if config.screenshot_retention_days > 0:
                logger.info("Cleaning up old screenshots...")
                retention_seconds = config.screenshot_retention_days * 86400
                now = time.time()
                for root, _, files in os.walk(config.screenshots_dir):
                    for file in files:
                        path = os.path.join(root, file)
                        if now - os.path.getctime(path) > retention_seconds:
                            try:
                                os.remove(path)
                            except Exception as e:
                                logger.error(f"Failed to delete old screenshot {path}: {e}")
                                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in background summarization job: %s", e)

async def _bounded_job_wrapper(job_id: str, text: str, webhook_url: str = None):
    async with _JOB_SEMAPHORE:
        task = asyncio.create_task(run_job(job_id, text, webhook_url))
        active_job_tasks.add(task)
        task.add_done_callback(active_job_tasks.discard)
        await task

async def queue_worker():
    while True:
        try:
            job_id, job_data_str = await job_queue.get()
            logger.info("Worker picked up job %s", job_id)
            
            # Parse payload to extract text and webhook
            try:
                job_data = json.loads(job_data_str)
                text = job_data.get("text", job_data_str)
                webhook_url = job_data.get("webhook_url")
            except json.JSONDecodeError:
                text = job_data_str
                webhook_url = None
                
            task = asyncio.create_task(_bounded_job_wrapper(job_id, text, webhook_url))
            active_job_tasks.add(task)
            task.add_done_callback(active_job_tasks.discard)
            # Add exception handler to log any unhandled exceptions
            def _handle_task_exception(t):
                try:
                    t.result()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error("Unhandled exception in job task %s: %s", job_id, e)
            task.add_done_callback(_handle_task_exception)
            job_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in queue worker: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator, job_store, job_queue
    logger.info("Initializing Framework Orchestrator for API...")
    orchestrator = FrameworkBuilder.build_orchestrator()
    job_store = JobStore()
    await job_store.connect()
    
    # Recover queued jobs from previous run
    recovered_jobs = await job_store.get_queued_jobs()
    for job in recovered_jobs:
        job_queue.put_nowait((job["job_id"], job.get("payload", "")))
        logger.info("Recovered queued job: %s", job["job_id"])
        
    def on_state_changed(event: TaskStateChangedEvent):
        # Only update if job is not already in a terminal state to avoid race conditions
        async def _update():
            job = await job_store.get_job(event.job_id)
            if job and job["status"] not in ("COMPLETED", "FAILED", "CANCELLED"):
                await job_store.update_job(event.job_id, f"RUNNING ({event.new_state})")
        task = asyncio.create_task(_update())
        active_job_tasks.add(task)
        task.add_done_callback(active_job_tasks.discard)
        def _handle_task_exception(t):
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("Unhandled exception in state update task: %s", e)
        task.add_done_callback(_handle_task_exception)
        
    orchestrator.engine.event_bus.subscribe("task_state_changed", on_state_changed)
    
    # Start background tasks
    summarize_task = asyncio.create_task(background_summarization_job())
    worker_task = asyncio.create_task(queue_worker())
    
    yield
    
    logger.info("Shutting down Framework Orchestrator...")
    summarize_task.cancel()
    worker_task.cancel()
    
    logger.info("Draining in-flight jobs...")
    
    # Wait for the queue worker to finish current tasks, up to 30 seconds
    try:
        await asyncio.wait_for(job_queue.join(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("Timeout while waiting for job queue to drain.")

    # Anything still in active_job_tasks is interrupted. We need to manually set them to FAILED.
    # Note: the job_id isn't trivially accessible from the task object here, so a better approach
    # is to have run_job handle its own cancellation.
    for task in list(active_job_tasks):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
    if hasattr(orchestrator.step_runner, "executor"):
        await orchestrator.step_runner.executor.shutdown()
        
    await job_store.close()

app = FastAPI(
    title="Local Multi-Agent Framework API",
    description="Asynchronous API for triggering agent tasks remotely",
    version="1.0.0",
    docs_url="/v1/docs",
    openapi_url="/v1/openapi.json",
    lifespan=lifespan
)

@app.middleware("http")
async def limit_payload_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB
        from core.logger import get_task_id
        return Response(
            content=json.dumps(ErrorResponse(
                error_code=ErrorCode.PAYLOAD_TOO_LARGE,
                message="Payload too large (10MB limit)",
                request_id=get_task_id()
            ).model_dump()),
            status_code=413,
            media_type="application/json"
        )
    return await call_next(request)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    set_task_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    REQUEST_LATENCY.observe(duration)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    return response

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import time

def _validate_webhook_url(url: str) -> bool:
    """Basic SSRF protection for webhook URLs."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        # Block localhost/private IPs in production
        if os.environ.get("ENV") == "production":
            hostname = parsed.hostname or ""
            if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or hostname.startswith("10.") or hostname.startswith("192.168.") or hostname.startswith("172.16."):
                return False
        return True
    except Exception:
        return False

async def run_job(job_id: str, text: str, webhook_url: str = None):
    start_time = time.time()
    await job_store.update_job(job_id, "RUNNING")
    status_label = "FAILED"
    result = None
    try:
        # Check cancellation before starting
        if cancellation_tokens.get(job_id):
            status_label = "CANCELLED"
            result = "Job cancelled before start"
            await job_store.update_job(job_id, "CANCELLED", result=result)
            return
        
        # Run the job and capture actual success/failure
        success = await orchestrator.process_prompt(text, job_id=job_id)
        if success:
            status_label = "COMPLETED"
            result = "Task completed successfully"
        else:
            status_label = "FAILED"
            result = "Task failed"
        await job_store.update_job(job_id, status_label, result=result)
    except CircuitBreakerOpenError as e:
        logger.error("Job %s failed fast due to circuit breaker: %s", job_id, e)
        result = str(e)
        await job_store.update_job(job_id, "FAILED", result=result)
    except asyncio.CancelledError:
        logger.error("Job %s cancelled during shutdown", job_id)
        result = "System shutdown"
        await job_store.update_job(job_id, "FAILED", result=result)
    except Exception as e:
        result = str(e)
        await job_store.update_job(job_id, "FAILED", result=result)
    finally:
        JOB_DURATION.labels(status=status_label).observe(time.time() - start_time)
        if webhook_url and _validate_webhook_url(webhook_url):
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(webhook_url, json={
                        "job_id": job_id,
                        "status": status_label,
                        "result": result,
                        "completed_at": datetime.datetime.now(timezone.utc).isoformat()
                    }, timeout=5.0)
            except Exception as w_e:
                logger.error("Failed to post webhook for job %s to %s: %s", job_id, webhook_url, w_e)
        elif webhook_url:
            logger.warning("Webhook URL failed validation, not sending: %s", webhook_url)

v1_router = APIRouter(prefix="/v1")

@v1_router.post("/prompt", status_code=202)
@limiter.limit("10/minute")
async def process_prompt(request: PromptRequest, req: Request, api_key: str = Depends(get_api_key)):
    """
    Submits a prompt to the agent framework for background processing.
    """
    logger.info(f"API received prompt: {request.text}")
    job_id = str(uuid.uuid4())
    await job_store.create_job(job_id, request.text, request.webhook_url)
    
    # Push to in-memory queue for worker to pick up
    job_data = json.dumps({"text": request.text, "webhook_url": request.webhook_url})
    await job_queue.put((job_id, job_data))
    
    return {"job_id": job_id, "status": "queued"}

@v1_router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, api_key: str = Depends(get_api_key)):
    job = await job_store.get_job(job_id)
    if not job or job["status"] not in ("QUEUED", "RUNNING"):
        from core.logger import get_task_id
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code=ErrorCode.JOB_NOT_FOUND,
                message="Job not cancellable or not found",
                request_id=get_task_id()
            ).model_dump()
        )
    
    cancellation_tokens[job_id] = True
    
    # If job is running, signal the step runner to cancel
    if job["status"] == "RUNNING" and orchestrator and hasattr(orchestrator, "step_runner"):
        orchestrator.step_runner.cancel()
    
    # Update job status to CANCELLED
    await job_store.update_job(job_id, "CANCELLED", result="Cancelled by user")
    return {"job_id": job_id, "status": "CANCELLED"}

@v1_router.get("/status/{job_id}")
async def get_status(job_id: str, api_key: str = Depends(get_api_key)):
    """
    Get the status of a job.
    """
    job = await job_store.get_job(job_id)
    if not job:
        from core.logger import get_task_id
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error_code=ErrorCode.JOB_NOT_FOUND,
                message=f"Job {job_id} not found",
                request_id=get_task_id()
            ).model_dump()
        )
    return job

app.include_router(v1_router)

@app.get("/metrics")
async def get_metrics():
    """
    Prometheus metrics endpoint.
    """
    return Response(generate_latest(), media_type="text/plain")

@app.get("/health")
async def health_check():
    """
    Deep health check endpoint.
    """
    health = {
        "status": "healthy",
        "manager_model": config.manager_model,
        "worker_model": config.worker_model,
        "vision_model": config.vision_model,
        "checks": {}
    }
    
    # Check SQLite
    try:
        # Just run a quick pragma to see if DB is responsive
        def _check_sqlite():
            conn = sqlite3.connect(job_store.db_path)
            try:
                conn.execute("PRAGMA user_version").fetchone()
            finally:
                conn.close()
        await asyncio.to_thread(_check_sqlite)
        health["checks"]["sqlite"] = "ok"
    except Exception as e:
        health["checks"]["sqlite"] = f"error: {str(e)}"
        health["status"] = "degraded"
        
    # Check Ollama
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(config.ollama_base_url, timeout=2.0)
            if resp.status_code == 200:
                health["checks"]["ollama"] = "ok"
            else:
                health["checks"]["ollama"] = f"error: status {resp.status_code}"
                health["status"] = "degraded"
    except Exception as e:
        health["checks"]["ollama"] = f"error: {str(e)}"
        health["status"] = "degraded"
        
    # Check ChromaDB
    try:
        if orchestrator and orchestrator.memory and orchestrator.memory.chroma:
            # Quick pulse check
            orchestrator.memory.chroma.heartbeat()
            health["checks"]["chroma"] = "ok"
    except Exception as e:
        health["checks"]["chroma"] = f"error: {str(e)}"
        health["status"] = "degraded"

    return health
