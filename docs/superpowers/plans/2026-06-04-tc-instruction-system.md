# TC Instruction System Enhancement Plan

> **机制编号：** 2.6 | **优先级：** P1 | **预估工时：** 1 天

## 目标

为 TC 的 AI Agent 添加动态指令注入系统，允许根据当前任务类型（测试/搭建/查错/优化）和环境状态选择性激活相关指令集，提高 Agent 的指令执行准确率。

## 背景

Opencode 的 `session/instruction.ts` 实现了动态指令注入：根据 Agent 运行状态选择性激活/禁用指令。TC 的 `AI_INSTRUCTIONS.md` 定义了一套完整的指令协议（约 200 行），但所有指令总是全部注入到 system prompt 中，无法根据当前场景动态调整。Agent 面对大量指令时可能选择错误工具或遗漏适用指令。

## 设计

### 核心思路

将指令集按场景分组，根据 Agent 当前任务类型动态加载对应指令组。保持全量指令可用性，但只在 system prompt 中突出当前场景最相关的指令。

### 指令分组

```
基础指令（always injected）：
  - SIM, SAMPLE, GET_INFO (读状态)
  - ADD, WIRE, MOVE, DEL (基本搭建)

测试场景（test）：
  - SET, TOGGLE (设置输入)
  - 真值表生成步骤说明

查错场景（debug）：
  - 视觉检查提示（端口/悬空线）
  - 信号追踪步骤

模块化场景（module）：
  - DEFINE_MODULE (封装模块)
  - 端口规划指导

优化场景（optimize）：
  - 逻辑化简步骤
  - 冗余检测提示
```

### 文件结构

| 文件 | 说明 |
|------|------|
| `instructions.py` | 新增：指令系统核心逻辑 |
| `AI_INSTRUCTIONS.md` | 修改：补充场景化指令段标注 |

### instructions.py 设计

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InstructionGroup:
    id: str
    name: str
    content: str
    scenario: str  # "always" | "test" | "debug" | "module" | "optimize"
    priority: int = 0  # 越高越优先注入


class InstructionManager:
    def __init__(self, base_file: str = "AI_INSTRUCTIONS.md"):
        self.base_file = base_file
        self._groups: dict[str, InstructionGroup] = {}
        self._load()

    def _load(self):
        """从 AI_INSTRUCTIONS.md 加载指令组（按 %%SCENARIO:xxx%% 标记解析）"""
        # 实现细节...

    def build_prompt_section(self, scenarios: list[str]) -> str:
        """
        构建包含以下部分的指令段：
        1. 基础指令（always）— 必须
        2. 活跃场景指令 — 前置突出
        3. 其他场景指令 — 作为参考附录
        """
        ordered = []

        # 基础指令
        ordered.append(self._groups.get("always", None))

        # 当前活跃场景指令（按优先级排序）
        active = [g for g in self._groups.values() if g.scenario in scenarios]
        active.sort(key=lambda g: g.priority, reverse=True)
        ordered.extend(active)

        # 其他场景指令（简要参考）
        # ...

        return "\n\n".join(g.content for g in ordered if g)

    def list_scenarios(self) -> list[str]:
        return list(set(g.scenario for g in self._groups.values() if g.scenario != "always"))
```

### AI_INSTRUCTIONS.md 标注格式

```markdown
## 指令集

%%SCENARIO:always%%
### 基础指令
...

%%SCENARIO:test%%
### 测试场景指令
- SET <id> <0|1>
- SIM
- SAMPLE [id ...]
...

%%SCENARIO:debug%%
### 查错场景指令
...
```

### app.py 集成

```python
from instructions import InstructionManager

instr_mgr = InstructionManager()

def _build_autonomous_system_prompt(task_type: str = None):
    # 根据任务类型确定活跃场景
    scenarios = task_to_scenarios(task_type)  # e.g., "testing" → ["test"]
    instructions_section = instr_mgr.build_prompt_section(scenarios)
    # ...
```

## 任务分解

- [ ] 1. 在 `AI_INSTRUCTIONS.md` 中添加 %%SCENARIO:xxx%% 场景标注
- [ ] 2. 创建 `instructions.py` — `InstructionManager._load()` 解析标注
- [ ] 3. 实现 `build_prompt_section()` 按场景组装指令
- [ ] 4. 实现 `task_to_scenarios()` 映射函数（任务类型 → 场景列表）
- [ ] 5. 修改 `_build_autonomous_system_prompt()` 动态加载指令
- [ ] 6. 测试：Agent 在不同任务场景下 system prompt 包含不同指令高亮
- [ ] 7. 提交 commit

## 关键决策

- **全量可用 vs 突出高亮**：所有指令 Agent 始终可调用，但对当前场景最相关的指令在 system prompt 中靠前/突出显示
- **解析标记**：使用 `%%SCENARIO:xxx%%` 标记（简明的自定义标记，无须引入 YAML 解析器）
- **场景检测**：基于 `_quick_classify()` 的输出（test/chat 模式）+ 用户最近消息的关键词
- **不做**：指令权限化（某些场景才可用），全量指令仍然全部可用
