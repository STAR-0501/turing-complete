"""TC 电路模拟器的子代理生命周期管理。

提供带并发任务限制的线程化子代理执行。
子代理是轻量级一次性 LLM 调用，用于并行电路任务。
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

from _common import load_ai_config, build_api_url

logger = logging.getLogger(__name__)

# 最大并发子代理任务数
MAX_CONCURRENT = 3
# 每个任务的执行超时（秒）
TASK_TIMEOUT = 120


def _call_llm(system_prompt, user_message):
    """子代理任务的简化非流式 LLM 调用。

    镜像 app.py 的 _call_llm_once，但只返回文本内容。
    """
    config = load_ai_config()
    api_key = config.get("api_key", "")
    if not api_key:
        raise RuntimeError("AI API key not configured")

    protocol = config.get("protocol", "")

    if protocol == "anthropic":
        request_url = build_api_url('/v1/messages')
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
        request_url = build_api_url('/chat/completions')
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
    """表示单个子代理执行任务。"""
    id: str
    goal: str
    circuit_snapshot: dict
    status: str  # "pending" | "running" | "completed" | "failed"
    result: Optional[str] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None


class SubagentManager:
    """管理子代理生命周期，带有并发任务限制。

    允许主代理最多生成 MAX_CONCURRENT 个子代理任务，
    在后台线程中运行。超出部分通过信号量排队。
    """

    def __init__(self):
        self._tasks: dict[str, SubagentTask] = {}
        self._semaphore = threading.Semaphore(MAX_CONCURRENT)

    def create(self, goal, snapshot):
        """创建并启动一个子代理任务。

        参数:
            goal: 给子代理的自然语言目标。
            snapshot: 电路快照字典（来自 CircuitManager.export_snapshot）。

        返回:
            task_id 字符串（例如 "sa_abc123def456"）。
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
        """获取任务状态字典，如果未找到返回 None。

        返回:
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
        """在后台线程中执行子代理任务。

        获取信号量槽位，调用 LLM，保存结果或错误。
        """
        task = self._tasks.get(task_id)
        if not task:
            return

        # 获取并发槽位（带超时）
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
