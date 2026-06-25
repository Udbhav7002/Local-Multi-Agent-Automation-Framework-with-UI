"""
Asynchronous API Layer for the Local Multi-Agent Automation Framework.
"""
import os
import asyncio
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

# Global orchestrator instance
orchestrator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    logger.info("Initializing Framework Orchestrator for API...")
    orchestrator = FrameworkBuilder.build_orchestrator()
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

@app.post("/prompt", status_code=202)
async def process_prompt(request: PromptRequest, api_key: str = Depends(get_api_key)):
    """
    Submits a prompt to the agent framework for background processing.
    """
    logger.info(f"API received prompt: {request.text}")
    # Queue the task in the background so the HTTP request doesn't block indefinitely
    asyncio.create_task(orchestrator.process_prompt(request.text))
    return {"status": "accepted", "message": "Task queued for execution."}

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
