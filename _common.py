"""Shared utilities for Turing Complete — extracted to eliminate code redundancy.

Consolidates duplicated functions that previously lived in multiple files:
- atomic_write_json (was in app.py + ai_commands.py)
- AI config helpers (was in app.py + subagent_manager.py)
- build_api_url (was in app.py + subagent_manager.py)
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from typing import Any

# ──────────────────────────────────────────────
# Atomic file I/O
# ──────────────────────────────────────────────


def _atomic_write(path: str, write_func) -> None:
    """原子写入的通用实现：临时文件 + os.replace。

    Args:
        path: 目标文件路径。
        write_func: 接受一个已打开的文件对象并写入内容的可调用对象。
    """
    for stale in glob.glob(f"{path}.tmp.*"):
        try:
            os.remove(stale)
        except OSError:
            pass
    dir_name = os.path.dirname(path) or os.getcwd()
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dir_name,
        prefix=f".{os.path.basename(path)}.tmp.",
        delete=False,
    ) as f:
        write_func(f)
        f.flush()
        os.fsync(f.fileno())
        tmp_path = f.name
    try:
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, data: Any) -> None:
    """Atomically write JSON data to a file using temp file + os.replace.

    Args:
        path: Destination file path.
        data: JSON-serializable data to write.
    """
    _atomic_write(path, lambda f: json.dump(data, f, indent=2, ensure_ascii=False))


def atomic_write_text(path: str, content: str) -> None:
    """Atomically write plain text to a file using temp file + os.replace.

    Args:
        path: Destination file path.
        content: Text content to write.
    """
    _atomic_write(path, lambda f: f.write(content))


# ──────────────────────────────────────────────
# AI Configuration (single source of truth)
# ──────────────────────────────────────────────

CONFIG_FILE = "ai_config.json"

_AI_CONFIG_DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "max_tokens": 4000,
    "connect_timeout": 10,
    "read_timeout": 180,
    "protocol": "",
    "anthropic_version": "2023-06-01",
    "agent_max_rounds": 100,
    "agent_max_cmds_per_round": 200,
    "agent_no_progress_stop_rounds": 30,
}

_ai_config_cache: dict[str, Any] | None = None


def load_ai_config() -> dict[str, Any]:
    """从 ai_config.json 加载 AI 配置。"""
    global _ai_config_cache
    config = dict(_AI_CONFIG_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    _ai_config_cache = config
    return config


def get_ai_config() -> dict[str, Any]:
    """获取 AI 配置（含缓存）。"""
    global _ai_config_cache
    if _ai_config_cache is None:
        return load_ai_config()
    return _ai_config_cache


def save_ai_config(data: dict[str, Any]) -> dict[str, Any]:
    """更新并持久化 AI 配置。"""
    global _ai_config_cache
    config = get_ai_config()
    config.update(data)
    atomic_write_json(CONFIG_FILE, config)
    _ai_config_cache = config
    return config


def is_ai_configured() -> bool:
    """检查 AI 是否已配置有效的 API Key。"""
    cfg = get_ai_config()
    key = cfg.get("api_key", "")
    return bool(key) and key != "YOUR_API_KEY_HERE"


def build_api_url(endpoint: str, base_url: str | None = None) -> str:
    """构建 API URL，防止重复拼接路径。"""
    if base_url is None:
        base_url = get_ai_config()['base_url']
    base = str(base_url).rstrip('/')
    if base.endswith(endpoint):
        return base
    return f"{base}{endpoint}"


def load_ai_config() -> dict[str, Any]:
    """Load AI config from ai_config.json, falling back to defaults."""
    global _ai_config_cache
    config = dict(_AI_CONFIG_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        config.update(file_config)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    _ai_config_cache = config
    return config


def get_ai_config() -> dict[str, Any]:
    """Get cached AI config, loading on first call."""
    global _ai_config_cache
    if _ai_config_cache is None:
        return load_ai_config()
    return _ai_config_cache


def save_ai_config(data: dict[str, Any]) -> dict[str, Any]:
    """Update and persist AI config. Returns the full updated config."""
    global _ai_config_cache
    config = get_ai_config()
    config.update(data)
    atomic_write_json(CONFIG_FILE, config)
    _ai_config_cache = config
    return config


def is_ai_configured() -> bool:
    """Check whether a valid API key is set."""
    cfg = get_ai_config()
    key = cfg.get("api_key", "")
    return bool(key) and key != "YOUR_API_KEY_HERE"


def build_api_url(endpoint: str, base_url: str | None = None) -> str:
    """Build API URL, preventing double path concatenation.

    Args:
        endpoint: API path, e.g. '/chat/completions'.
        base_url: Optional custom base URL; defaults to saved config.

    Returns:
        Fully qualified API URL.
    """
    if base_url is None:
        base_url = get_ai_config()["base_url"]
    base = str(base_url).rstrip("/")
    if base.endswith(endpoint):
        return base
    return f"{base}{endpoint}"
