"""
Asynchronous API Layer for the Local Multi-Agent Automation Framework.
"""
import os
import asyncio
import uuid
import sqlite3
import json
import datetime
from datetime import timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from core.factory import FrameworkBuilder
from core.config import config
from core.logger import setup_logger

logger = setup_logger("API")

API_KEY = os.environ.get("AGENT_API_KEY", "local-dev-key")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    return api_key_header

class PromptRequest(BaseModel):
    text: str

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_JOBS_DB_PATH = os.path.join(_PROJECT_ROOT, "jobs.db")

class JobStore:
    def __init__(self, db_path=_JOBS_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT,
                    result TEXT,
                    steps_executed TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def create_job(self, job_id: str) -> None:
        now = datetime.datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (job_id, "QUEUED", now, now)
            )
            conn.commit()

    def update_job(self, job_id: str, status: str, result: str = None, steps_executed: list = None) -> None:
        now = datetime.datetime.now(timezone.utc).isoformat()
        steps_str = json.dumps(steps_executed) if steps_executed is not None else None
        with sqlite3.connect(self.db_path) as conn:
            if result is not None and steps_executed is not None:
                conn.execute(
                    "UPDATE jobs SET status = ?, result = ?, steps_executed = ?, updated_at = ? WHERE job_id = ?",
                    (status, result, steps_str, now, job_id)
                )
            elif result is not None:
                conn.execute(
                    "UPDATE jobs SET status = ?, result = ?, updated_at = ? WHERE job_id = ?",
                    (status, result, now, job_id)
                )
            elif steps_executed is not None:
                conn.execute(
                    "UPDATE jobs SET status = ?, steps_executed = ?, updated_at = ? WHERE job_id = ?",
                    (status, steps_str, now, job_id)
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (status, now, job_id)
                )
            conn.commit()

    def get_job(self, job_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

# Global orchestrator instance
orchestrator = None
job_store = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator, job_store
    logger.info("Initializing Framework Orchestrator for API...")
    orchestrator = FrameworkBuilder.build_orchestrator()
    job_store = JobStore()
    yield
    logger.info("Shutting down Framework Orchestrator...")
    if hasattr(orchestrator.step_runner, "executor"):
        await orchestrator.step_runner.executor.shutdown()

app = FastAPI(
    title="Local Multi-Agent Framework API",
    description="Asynchronous API for triggering agent tasks remotely",
    version="1.0.0",
    lifespan=lifespan
)

async def run_job(job_id: str, text: str):
    await asyncio.to_thread(job_store.update_job, job_id, "RUNNING")
    try:
        result = await orchestrator.process_prompt(text)
        await asyncio.to_thread(job_store.update_job, job_id, "COMPLETED", result=str(result))
    except Exception as e:
        await asyncio.to_thread(job_store.update_job, job_id, "FAILED", result=str(e))

@app.post("/prompt", status_code=202)
async def process_prompt(request: PromptRequest, api_key: str = Depends(get_api_key)):
    """
    Submits a prompt to the agent framework for background processing.
    """
    logger.info(f"API received prompt: {request.text}")
    job_id = str(uuid.uuid4())
    await asyncio.to_thread(job_store.create_job, job_id)
    # Queue the task in the background so the HTTP request doesn't block indefinitely
    asyncio.create_task(run_job(job_id, request.text))
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
async def get_status(job_id: str, api_key: str = Depends(get_api_key)):
    """
    Get the status of a job.
    """
    job = await asyncio.to_thread(job_store.get_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "healthy",
        "manager_model": config.manager_model,
        "worker_model": config.worker_model,
        "vision_model": config.vision_model
    }
