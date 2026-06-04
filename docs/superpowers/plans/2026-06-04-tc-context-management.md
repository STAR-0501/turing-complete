# TC Context Management Implementation Plan

> **机制编号：** 2.1 | **优先级：** P0 | **预估工时：** 1–2 天

## 目标

为 TC 的 AI Agent 添加上下文压实（Context Compaction）和溢出检测（Overflow Detection），让 Agent 能在长对话中保持有效工作状态，避免 token 耗尽导致退化。

## 背景

Opencode 的 `session/compaction.ts` 提供结构化压实到 Markdown 的能力，`session/overflow.ts` 提供溢出检测（基于阈值+增量模式）。TC 的 `app.py` 中 Agent 循环为 5-mode 流式交互，context 完全由 LLM API 管理（DeepSeek），无任何客户端侧 compaction/overflow 机制。每次 SSE 流式交互累积整个会话历史，token 持续增长直至超限。

## 设计

### 核心思路

在 `app.py` 的 Agent 循环中插入 Compaction 和 Overflow 检查点：

- **Overflow Detection（溢出检测）**：在每次 LLM 调用前，估算当前会话的 token 用量（基于已发送消息的字符/指令数），若超过阈值则触发 Compaction。
- **Context Compaction（上下文压实）**：将历史对话压实为结构化摘要并替换原始消息，保留最关键的电路状态（拓扑、线网、模块定义）和任务进展（已完成/待完成）。

### 文件结构

| 文件 | 说明 |
|------|------|
| `turing_compactor.py` | 新增：Compaction 和 Overflow 检测的核心逻辑 |
| `app.py` | 修改：在 Agent 循环中集成 Compaction/Overflow 检查点 |

### turing_compactor.py 设计

```
turing_compactor/
├── __init__.py          # 导出接口
├── compactor.py         # ContextCompactor 类
└── overflow.py          # OverflowDetector 类
```

#### OverflowDetector

```python
class OverflowDetector:
    def __init__(self, soft_limit: int = 32000, hard_limit: int = 48000):
        self.soft_limit = soft_limit  # 触发 compact 的软上限
        self.hard_limit = hard_limit  # 触顶硬限制

    def estimate_tokens(self, messages: list[dict]) -> int:
        """基于字符数估算 token 数 (≈ chars / 3.5)"""
        total_chars = sum(len(m["content"] or "") for m in messages)
        return int(total_chars / 3.5)

    def should_compact(self, messages: list[dict]) -> bool:
        return self.estimate_tokens(messages) > self.soft_limit

    def is_overflow(self, messages: list[dict]) -> bool:
        return self.estimate_tokens(messages) > self.hard_limit
```

#### ContextCompactor

```python
class ContextCompactor:
    def compact(self, messages: list[dict]) -> list[dict]:
        """
        压实策略：
        1. 保留最后 1 轮完整对话（用户消息+AI响应）
        2. 将更早的对话压实为一条系统消息摘要
        3. 摘要包含：电路拓扑、当前任务进展、已完成的 build 步骤
        """
        # 实现细节...
```

### app.py 集成点

在 `call_llm_stream()` 或 `_build_autonomous_system_prompt()` 的循环中插入：

```python
# 在每次 LLM 调用前
overflow = OverflowDetector()
if overflow.should_compact(messages):
    compactor = ContextCompactor()
    messages = compactor.compact(messages)
```

## 任务分解

- [ ] 1. 创建 `turing_compactor/` 包结构（`__init__.py`, `compactor.py`, `overflow.py`）
- [ ] 2. 实现 `OverflowDetector.estimate_tokens()` 和 `should_compact()`
- [ ] 3. 实现 `ContextCompactor.compact()` — 基础压实逻辑（保留最新轮次 + 摘要历史）
- [ ] 4. 在 `app.py` 的 Agent 循环中集成 compaction 检查点
- [ ] 5. 测试人工：运行 Agent 执行多轮搭建任务，观察 compaction 触发
- [ ] 6. 提交 commit

## 关键决策

- **阈值估算**：soft_limit=32000, hard_limit=48000（基于 DeepSeek 64K context 预留余量）
- **压缩策略**：保留最新完整轮次 + 结构化摘要（而非保留所有轮次但截断）
- **摘要格式**：Markdown 格式，与 system prompt 保持一致风格
- **不采用** sliding window（丢失中间状态）或纯 truncation（丢失关键信息）
