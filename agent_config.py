"""Unified agent configuration with YAML support.

Provides AgentConfig dataclass that aggregates configuration
(model, retry, permissions, skills, subagent) into one place
with YAML config file support, while backward-compatibly
wrapping the existing ai_config.json system.

Usage:
    from agent_config import AgentConfig, get_agent_config

    cfg = AgentConfig.load()
    print(cfg.model_name)

    # Global singleton
    config = get_agent_config()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

from permissions import Permission


@dataclass
class AgentConfig:
    """Unified agent configuration with YAML + JSON fallback.

    Loads in order:
    1. agent_config.yaml (highest priority, user-editable)
    2. Hardcoded defaults (fallback)

    API settings (api_key, base_url, model) remain in ai_config.json
    via the existing get_ai_config() pattern — this class is a
    SUPPLEMENT for the new mechanisms (retry, permissions, skills,
    subagent, context limits).
    """

    # --- Model ---
    model_name: str = "deepseek-v4-flash"
    temperature: float = 0.7
    max_tokens: int = 4000

    # --- Retry ---
    retry_max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0

    # --- Context limits ---
    context_soft_limit_tokens: int = 32000
    context_hard_limit_tokens: int = 48000

    # --- Permissions ---
    permissions_default_level: str = "write"

    # --- Skills ---
    skills_dir: str = "skills"
    skills_auto_discover: bool = True

    # --- Subagent ---
    subagent_max_concurrent: int = 3
    subagent_default_timeout: int = 120

    # Internal
    _loaded_yaml: bool = False

    @classmethod
    def load(cls, yaml_path: str = "agent_config.yaml") -> "AgentConfig":
        """Load config from YAML file, falling back to defaults.

        Args:
            yaml_path: Path to YAML config file. If relative,
                       resolved relative to this file's directory
                       (the project root).

        Returns:
            Fully populated AgentConfig instance.
        """
        config = cls()

        # Resolve relative path against the project root
        if not os.path.isabs(yaml_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, yaml_path)

        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            agent_data = data.get("agent", {})
            config._apply_yaml(agent_data)
            config._loaded_yaml = True

        return config

    def _apply_yaml(self, data: dict) -> None:
        """Apply YAML data to this config instance."""
        if not data:
            return

        model = data.get("model", {})
        if "name" in model:
            self.model_name = model["name"]
        if "max_tokens" in model:
            self.max_tokens = int(model["max_tokens"])
        if "temperature" in model:
            self.temperature = float(model["temperature"])

        retry = data.get("retry", {})
        if "max_retries" in retry:
            self.retry_max_retries = int(retry["max_retries"])
        if "base_delay" in retry:
            self.retry_base_delay = float(retry["base_delay"])
        if "max_delay" in retry:
            self.retry_max_delay = float(retry["max_delay"])

        ctx = data.get("context", {})
        if "soft_limit_tokens" in ctx:
            self.context_soft_limit_tokens = int(ctx["soft_limit_tokens"])
        if "hard_limit_tokens" in ctx:
            self.context_hard_limit_tokens = int(ctx["hard_limit_tokens"])

        perm = data.get("permissions", {})
        if "default_level" in perm:
            self.permissions_default_level = perm["default_level"]

        skills = data.get("skills", {})
        if "dir" in skills:
            self.skills_dir = skills["dir"]
        if "auto_discover" in skills:
            self.skills_auto_discover = bool(skills["auto_discover"])

        sub = data.get("subagent", {})
        if "max_concurrent" in sub:
            self.subagent_max_concurrent = int(sub["max_concurrent"])
        if "default_timeout" in sub:
            self.subagent_default_timeout = int(sub["default_timeout"])

    @property
    def permission_enum(self) -> Permission:
        """Resolve permissions_default_level string to Permission enum."""
        mapping = {
            "read": Permission.READ,
            "exec": Permission.EXEC,
            "write": Permission.WRITE,
            "admin": Permission.ADMIN,
        }
        return mapping.get(self.permissions_default_level, Permission.WRITE)


# ---------------------------------------------------------------------------
# Module-level singleton access
# ---------------------------------------------------------------------------

_config_instance: Optional[AgentConfig] = None


def get_agent_config() -> AgentConfig:
    """Return the global AgentConfig singleton (lazy-loaded)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = AgentConfig.load()
    return _config_instance


def reload_agent_config() -> None:
    """Reload YAML config at runtime. Call after file changes."""
    global _config_instance
    _config_instance = AgentConfig.load()
