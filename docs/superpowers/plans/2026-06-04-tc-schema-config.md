# TC Schema Agent Configuration Plan

> **机制编号：** 2.7 | **优先级：** P1 | **预估工时：** 1 天

## 目标

为 TC 的 AI Agent 引入结构化配置能力，通过外部配置文件（YAML）定义 Agent 的行为参数（模型选择、重试策略、权限级别、技能加载规则），而非硬编码在 `app.py` 中。同时支持跨重启的会话状态持久化。

## 背景

Opencode 使用 Schema-first 方式定义 Agent 配置（`agent.ts` 中 config schema），配置参数清晰、可外部化。TC 的 Agent 配置目前完全硬编码在 `app.py` 的 `AI_CONFIG` 字典中（模型名称、API key、温度等），修改配置需要编辑 Python 文件。且 `plan.md` 和 `summary.md` 的持久化很简陋（纯 Markdown 文件覆盖写入）。

## 设计

### 核心思路

1. 引入 YAML 配置文件 `agent_config.yaml`，集中管理所有 Agent 参数
2. 将 `AI_CONFIG` 中的所有参数外部化
3. 扩展 plan/summary 持久化为结构化格式（YAML 或 JSON）
4. 支持运行时配置重载（无需重启服务）

### 文件结构

| 文件 | 说明 |
|------|------|
| `agent_config.yaml` | 新增：Agent 外部配置文件 |
| `agent_config.py` | 新增：配置加载/验证逻辑 |
| `app.py` | 修改：将硬编码配置替换为动态加载 |
| `plan.md` / `summary.md` | 保留（但增加结构化版本） |

### agent_config.yaml

```yaml
# Agent 配置
agent:
  model:
    provider: deepseek
    name: deepseek-chat
    temperature: 0.7
    max_tokens: 4096

  retry:
    max_retries: 3
    base_delay: 1.0
    max_delay: 30.0

  context:
    soft_limit_tokens: 32000
    hard_limit_tokens: 48000

  permissions:
    default_level: write  # read | exec | write | admin

  skills:
    dir: skills/
    auto_discover: true
    load_tags: [general]

  subagent:
    max_concurrent: 3
    default_timeout: 120

  persistence:
    plan_file: plan.md
    summary_file: summary.md
    format: markdown  # markdown | json
```

### agent_config.py 设计

```python
import os
import yaml
from typing import Any
from dataclasses import dataclass
from permissions import Permission


@dataclass
class AgentConfig:
    model_name: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 4096
    retry_max: int = 3
    retry_base_delay: float = 1.0
    context_soft_limit: int = 32000
    permissions_default: Permission = Permission.WRITE
    skills_dir: str = "skills"
    subagent_max: int = 3
    plan_file: str = "plan.md"

    @classmethod
    def load(cls, path: str = "agent_config.yaml") -> "AgentConfig":
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "AgentConfig":
        config = cls()
        agent_data = data.get("agent", {})
        # 字段映射...
        return config

    def reload(self, path: str = "agent_config.yaml"):
        """运行时重载配置，不重启服务"""
        new_config = self.load(path)
        vars(self).update(vars(new_config))
```

### app.py 集成

```python
from agent_config import AgentConfig

# 启动时加载
config = AgentConfig.load()

# 替换硬编码配置使用处
# AI_CONFIG 中的参数改为 config.model_name, config.temperature 等
```

### 会话持久化增强

保留 `plan.md` 和 `summary.md` 的 Markdown 格式兼容，同时添加结构化 JSON 版本：

```python
def save_plan_structured(plan_data: dict):
    """写入 plan.json（结构化）+ plan.md（可读）"""
    with open("plan.json", "w") as f:
        json.dump(plan_data, f, indent=2, ensure_ascii=False)
    with open("plan.md", "w") as f:
        f.write(format_plan_markdown(plan_data))
```

## 任务分解

- [ ] 1. 创建 `agent_config.yaml` — 编写默认配置
- [ ] 2. 创建 `agent_config.py` — 实现 AgentConfig 加载/验证/重载
- [ ] 3. 修改 `app.py` — 将 `AI_CONFIG` 等硬编码配置替换为 config 实例
- [ ] 4. 实现结构化 plan/summary 持久化（JSON + Markdown 双输出）
- [ ] 5. 实现运行时重载机制（通过 API 端点触发）
- [ ] 6. 测试：修改 YAML 配置后验证配置生效
- [ ] 7. 提交 commit

## 关键决策

- **格式选择 YAML**：相比 JSON 更可读、支持注释、适合人工编辑
- **配置分层**：`agent.model.name`, `agent.retry.max_retries` 等嵌套结构
- **向后兼容**：YAML 文件缺失时回退到默认值（行为不变）
- **重载机制**：通过 `/api/reload_config` 端点触发，不需要重启服务
- **敏感信息**：API key 仍然使用环境变量，不放入 YAML
