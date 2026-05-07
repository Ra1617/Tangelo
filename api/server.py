"""
FastAPI Backend — REST API for the AI Office Assistant.
Receives prompts from the GUI, delegates to the Orchestrator,
and streams status updates.
"""

import uuid
import time
import logging
import threading
from typing import Any

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import requests as http_requests

from config import OLLAMA_URL, OLLAMA_MODEL
from agent.orchestrator import Orchestrator

logger = logging.getLogger("api")

# ─────────────────────────────────────────────
#  APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="AI Office Assistant API",
    description="Local AI agent that automates Office tasks via Ollama + sub-agents",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    prompt: str
    context: dict | None = None


class TaskStatus(BaseModel):
    task_id: str
    status: str            # "running", "complete", "error"
    message: str
    steps_log: list[dict]
    result: dict | None = None


# ─────────────────────────────────────────────
#  IN-MEMORY TASK STORE
# ─────────────────────────────────────────────

_tasks: dict[str, TaskStatus] = {}
_orchestrator = Orchestrator()


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Health check — also verifies Ollama connectivity."""
    ollama_ok = False
    try:
        resp = http_requests.get(
            OLLAMA_URL.replace("/api/chat", "/api/tags"),
            timeout=5
        )
        ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "healthy",
        "ollama_connected": ollama_ok,
        "model": OLLAMA_MODEL,
        "timestamp": time.time(),
    }


@app.post("/execute")
def execute_prompt(req: ExecuteRequest):
    """
    Submit a prompt for execution.
    Returns task_id immediately — poll /status/{task_id} for progress.
    """
    task_id = str(uuid.uuid4())[:8]

    task = TaskStatus(
        task_id=task_id,
        status="running",
        message="Starting...",
        steps_log=[],
    )
    _tasks[task_id] = task

    # Run orchestrator in background thread
    thread = threading.Thread(
        target=_run_task,
        args=(task_id, req.prompt),
        daemon=True
    )
    thread.start()

    return {"task_id": task_id, "status": "accepted"}


@app.get("/status/{task_id}")
def get_status(task_id: str):
    """Poll task execution status."""
    task = _tasks.get(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}
    return task.model_dump()


@app.post("/execute_sync")
def execute_sync(req: ExecuteRequest):
    """
    Synchronous execution — blocks until complete.
    Used by the GUI for simpler integration.
    """
    orchestrator = Orchestrator()
    steps_log = []

    def status_cb(phase: str, message: str, data: dict | None = None):
        steps_log.append({
            "phase": phase,
            "message": message,
            "data": data,
            "timestamp": time.time(),
        })

    orchestrator.set_status_callback(status_cb)
    result = orchestrator.process(req.prompt)

    return {
        "success": result["success"],
        "message": result["message"],
        "plan": result.get("plan"),
        "files_created": result.get("files_created", []),
        "steps_log": steps_log,
    }


# ─────────────────────────────────────────────
#  BACKGROUND TASK RUNNER
# ─────────────────────────────────────────────

def _run_task(task_id: str, prompt: str):
    """Run orchestrator in background, updating task status."""
    task = _tasks[task_id]
    orchestrator = Orchestrator()

    def status_cb(phase: str, message: str, data: dict | None = None):
        task.message = message
        task.steps_log.append({
            "phase": phase,
            "message": message,
            "data": data,
            "timestamp": time.time(),
        })

    orchestrator.set_status_callback(status_cb)

    try:
        result = orchestrator.process(prompt)
        task.status = "complete" if result["success"] else "error"
        task.message = result["message"]
        task.result = result
    except Exception as e:
        logger.exception("Task %s failed", task_id)
        task.status = "error"
        task.message = f"❌ Fatal error: {e}"
