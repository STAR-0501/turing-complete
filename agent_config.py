"""统一代理配置，支持 YAML。

提供 AgentConfig 数据类，将配置（模型、重试、权限、技能、子代理）
聚合到一处，支持 YAML 配置文件，同时向后兼容现有的 ai_config.json 系统。

用法:
    from agent_config import AgentConfig, get_agent_config

    cfg = AgentConfig.load()
    print(cfg.model_name)

    # 全局单例
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
    """统一代理配置，YAML + JSON 回退。

    加载顺序:
    1. agent_config.yaml（最高优先级，用户可编辑）
    2. 硬编码默认值（回退）

    API 设置（api_key, base_url, model）保留在 ai_config.json
    中，通过现有的 get_ai_config() 模式访问——此类是对新机制
    （重试、权限、技能、子代理、上下文限制）的补充。
    """

    # --- 模型 ---
    model_name: str = "deepseek-v4-flash"
    temperature: float = 0.7
    max_tokens: int = 4000

    # --- 重试 ---
    retry_max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0

    # --- 上下文限制 ---
    context_soft_limit_tokens: int = 32000
    context_hard_limit_tokens: int = 48000

    # --- 权限 ---
    permissions_default_level: str = "write"

    # --- 技能 ---
    skills_dir: str = "skills"
    skills_auto_discover: bool = True

    # --- 子代理 ---
    subagent_max_concurrent: int = 3
    subagent_default_timeout: int = 120

    # 内部
    _loaded_yaml: bool = False

    @classmethod
    def load(cls, yaml_path: str = "agent_config.yaml") -> "AgentConfig":
        """从 YAML 文件加载配置，回退到默认值。

        参数:
            yaml_path: YAML 配置文件路径。如果是相对路径，
                       则基于此文件所在目录（项目根目录）解析。

        返回:
            填充完整的 AgentConfig 实例。
        """
        config = cls()

        # 根据项目根目录解析相对路径
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
        """将 YAML 数据应用到当前配置实例。"""
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
        """将权限默认级别字符串解析为 Permission 枚举。"""
        mapping = {
            "read": Permission.READ,
            "exec": Permission.EXEC,
            "write": Permission.WRITE,
            "admin": Permission.ADMIN,
        }
        return mapping.get(self.permissions_default_level, Permission.WRITE)


# ---------------------------------------------------------------------------
# 模块级单例访问
# ---------------------------------------------------------------------------

_config_instance: Optional[AgentConfig] = None


def get_agent_config() -> AgentConfig:
    """返回全局 AgentConfig 单例（懒加载）。"""
    global _config_instance
    if _config_instance is None:
        _config_instance = AgentConfig.load()
    return _config_instance


def reload_agent_config() -> None:
    """运行时重新加载 YAML 配置。文件变更后调用。"""
    global _config_instance
    _config_instance = AgentConfig.load()
