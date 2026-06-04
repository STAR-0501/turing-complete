# TC Subagent System Implementation Plan

> **机制编号：** 2.2 | **优先级：** P0 | **预估工时：** 1.5–2.5 天

## 目标

为 TC 新增子代理（Subagent）系统，允许主 Agent 在搭建电路时动态派发子代理执行并行任务（如同时测试多个子模块、并行连线），大幅提升复杂电路搭建效率。

## 背景

Opencode 的 `tool/task.ts` 实现了正式的子代理生成机制，包含权限继承、独立会话、结果返回。TC 当前为单一 Agent 串行执行模式：Agent 发出 build 指令 → 等待执行 → 观察结果 → 继续下一步。无法并行执行多个独立任务。

## 设计

### 核心思路

新增 `/api/subagent` 端点，允许主 Agent 通过 JSON 命令派发子任务。子代理是轻量级的一次性 Agent 实例，拥有独立的会话上下文（携带共享的电路快照和指令集），执行完毕后返回结果。

### API 设计

**创建子代理：**
```
POST /api/subagent
{
    "goal": "验证HalfAdder模块的真值表",
    "context": {
        "circuit_snapshot": "...",  // 当前电路拓扑快照
        "instructions": "..."       // 指令集引用
    }
}
→ {"subagent_id": "sa_xxx", "status": "running"}
```

**查询子代理状态：**
```
GET /api/subagent/<id>
→ {"subagent_id": "sa_xxx", "status": "completed", "result": "..."}
```

### 文件结构

| 文件 | 说明 |
|------|------|
| `app.py` | 新增子代理 API 路由（/api/subagent 提交/查询） |
| `subagent_manager.py` | 新增：子代理生命周期管理 |
| `ai_commands.py` | 修改：暴露 CircuitManager 快照能力用于子代理上下文 |

### subagent_manager.py 设计

```python
import uuid
import threading
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SubagentTask:
    id: str
    goal: str
    circuit_snapshot: dict
    status: str  # "pending" | "running" | "completed" | "failed"
    result: Optional[str] = None
    thread: Optional[threading.Thread] = None
    error: Optional[str] = None


class SubagentManager:
    def __init__(self):
        self._tasks: dict[str, SubagentTask] = {}

    def create(self, goal: str, snapshot: dict) -> str:
        """创建并启动子代理任务"""
        task_id = f"sa_{uuid.uuid4().hex[:12]}"
        task = SubagentTask(id=task_id, goal=goal, circuit_snapshot=snapshot, status="pending")
        self._tasks[task_id] = task
        # 在独立线程中执行 LLM 调用
        thread = threading.Thread(target=self._execute, args=(task_id,))
        thread.start()
        return task_id

    def get_status(self, task_id: str) -> Optional[dict]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {"id": task.id, "status": task.status, "result": task.result, "error": task.error}

    def _execute(self, task_id: str):
        """在线程中执行子代理 LLM 调用（调用_quick_classify模式）"""
        # 实现细节：使用子 session 调用 LLM，不干扰主会话
        pass
```

### 主 Agent 集成

在 AI_INSTRUCTIONS.md 中新增指令格式：

```
SPAWN_SUBAGENT <goal>
→ 派发子代理执行独立任务，不影响主代理执行流程

CHECK_SUBAGENT <id>
→ 查询子代理执行状态

WAIT_SUBAGENT <id>
→ 同步等待子代理完成并返回结果
```

## 任务分解

- [ ] 1. 创建 `subagent_manager.py` — SubagentManager 核心类
- [ ] 2. 实现子代理独立 LLM 调用（复用 `call_llm_stream` 的简化版本）
- [ ] 3. 实现电路快照导出接口（在 `CircuitManager` 中添加 `export_snapshot()`）
- [ ] 4. 实现子代理结果收集和传递
- [ ] 5. 新增 `app.py` 路由 `/api/subagent`（创建+查询）
- [ ] 6. 更新 `AI_INSTRUCTIONS.md` 添加 SPAWN_SUBAGENT/CHECK_SUBAGENT/WAIT_SUBAGENT 指令
- [ ] 7. 测试：主 Agent 构建复杂电路时派发子代理测试子模块
- [ ] 8. 提交 commit

## 关键决策

- **线程模型**：每个子代理运行在独立线程中，共享 CircuitManager 的读快照（非写权限）
- **结果收集**：子代理完成后结果存储在 SubagentManager 中，主 Agent 通过指令轮询
- **快照隔离**：子代理获得电路快照（当前拓扑和值），但不允许直接修改主电路
- **超时**：子代理默认 120s 超时，超时自动标记为 failed
- **数量限制**：同时活跃子代理最多 3 个
