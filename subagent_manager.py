"""Subagent lifecycle management for TC circuit simulator.

Provides threaded subagent execution with concurrent task limiting.
Subagents are lightweight one-shot LLM calls for parallel circuit tasks.
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Max concurrent subagent tasks
MAX_CONCURRENT = 3
# Per-task execution timeout in seconds
TASK_TIMEOUT = 120

# AI config file path (same convention as app.py)
CONFIG_FILE = "ai_config.json"

_AI_CONFIG_DEFAULTS = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "max_tokens": 4000,
    "connect_timeout": 10,
    "read_timeout": 180,
    "protocol": "",
    "anthropic_version": "2023-06-01"
}


def _load_config():
    """Load AI config from ai_config.json (mirrors app.py helpers)."""
    config = dict(_AI_CONFIG_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return config


def _build_api_url(endpoint, base_url=None):
    """Build API URL (mirrors app.py helper)."""
    if base_url is None:
        base_url = _load_config()['base_url']
    base = str(base_url).rstrip('/')
    if base.endswith(endpoint):
        return base
    return f"{base}{endpoint}"


def _call_llm(system_prompt, user_message):
    """Simplified non-streaming LLM call for subagent tasks.

    Mirrors app.py _call_llm_once but returns only text content.
    """
    config = _load_config()
    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("AI API key not configured")

    protocol = config.get("protocol", "")

    if protocol == "anthropic":
        request_url = _build_api_url('/v1/messages')
        request_headers = {
            "x-api-key": api_key,
            "anthropic-version": config.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": config["model"],
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "temperature": 0.2,
            "max_tokens": int(config.get("max_tokens", 4000)),
            "stream": False
        }
    else:
        request_url = _build_api_url('/chat/completions')
        request_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        request_payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.2,
            "max_tokens": int(config.get("max_tokens", 4000)),
            "stream": False
        }

    connect_timeout = float(config.get("connect_timeout", 10))
    read_timeout = float(config.get("read_timeout", 180))

    response = requests.post(
        request_url,
        headers=request_headers,
        json=request_payload,
        timeout=(connect_timeout, read_timeout)
    )
    response.raise_for_status()
    payload = response.json()

    if protocol == "anthropic":
        content = payload.get("content") or []
        text = ''.join([c.get("text", "")
                       for c in content if isinstance(c, dict)])
        return text

    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


@dataclass
class SubagentTask:
    """Represents a single subagent execution task."""
    id: str
    goal: str
    circuit_snapshot: dict
    status: str  # "pending" | "running" | "completed" | "failed"
    result: Optional[str] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None


class SubagentManager:
    """Manages subagent lifecycle with concurrent task limiting.

    Allows the main agent to spawn up to MAX_CONCURRENT subagent tasks
    running in background threads. Excess tasks are queued via semaphore.
    """

    def __init__(self):
        self._tasks: dict[str, SubagentTask] = {}
        self._semaphore = threading.Semaphore(MAX_CONCURRENT)

    def create(self, goal, snapshot):
        """Create and start a subagent task.

        Args:
            goal: Natural language goal for the subagent.
            snapshot: Circuit snapshot dict (from CircuitManager.export_snapshot).

        Returns:
            task_id string (e.g. "sa_abc123def456").
        """
        task_id = f"sa_{uuid.uuid4().hex[:12]}"
        task = SubagentTask(
            id=task_id,
            goal=goal,
            circuit_snapshot=snapshot,
            status="pending"
        )
        self._tasks[task_id] = task
        thread = threading.Thread(target=self._execute, args=(task_id,))
        thread.daemon = True
        task.thread = thread
        thread.start()
        logger.info("Subagent task %s started: goal=%s", task_id, goal[:80])
        return task_id

    def get_status(self, task_id):
        """Get task status dict, or None if not found.

        Returns:
            {"id": str, "status": str, "result": str|None, "error": str|None}
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "id": task.id,
            "status": task.status,
            "result": task.result,
            "error": task.error
        }

    def _execute(self, task_id):
        """Execute subagent task in background thread.

        Acquires semaphore slot, calls LLM, saves result or error.
        """
        task = self._tasks.get(task_id)
        if not task:
            return

        # Acquire concurrent slot (with timeout)
        acquired = self._semaphore.acquire(blocking=True, timeout=TASK_TIMEOUT)
        if not acquired:
            task.status = "failed"
            task.error = f"Timeout waiting for concurrent slot ({TASK_TIMEOUT}s)"
            logger.warning("Subagent %s failed: semaphore timeout", task_id)
            return

        try:
            task.status = "running"
            logger.debug("Subagent %s executing (goal: %s)", task_id, task.goal[:60])

            system_prompt = (
                f"You are a circuit design assistant working in the Turing Complete simulator.\n\n"
                f"## Goal\n{task.goal}\n\n"
                f"## Current Circuit State\n"
                f"```json\n{json.dumps(task.circuit_snapshot, indent=2, ensure_ascii=False)}\n```\n\n"
                f"Execute the goal using circuit commands. Return your analysis and commands."
            )
            user_message = task.goal

            result = _call_llm(system_prompt, user_message)
            task.status = "completed"
            task.result = result
            logger.info("Subagent %s completed successfully", task_id)

        except Exception as e:
            logger.error("Subagent task %s failed: %s", task_id, e)
            task.status = "failed"
            task.error = str(e)
        finally:
            self._semaphore.release()
