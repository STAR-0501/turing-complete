# TC Retry & Backoff Implementation Plan

> **机制编号：** 2.4 | **优先级：** P1 | **预估工时：** 0.5 天

## 目标

为 TC Agent 的 LLM API 调用和指令执行添加指数退避（Exponential Backoff）重试机制，提高 Agent 在 API 限流/临时错误/网络抖动下的鲁棒性。

## 背景

Opencode 的 `session/retry.ts` 实现了指数退避重试：支持最大重试次数、基础延迟、随机抖动。TC 的 `app.py` 中 `call_llm_stream()` 函数直接调用 DeepSeek API，没有任何重试逻辑——API 调用失败直接导致 Agent 循环终止丢回错误。`ai_commands.py` 的指令执行也无重试。

## 设计

### 核心思路

封装 LLM API 调用和指令执行为可重试操作，使用指数退避 + 随机抖动的策略：

- **LLM API 调用重试**：在 `call_llm_stream()` 中环绕重试逻辑
- **指令执行重试**：在 `ai_commands.py` 的执行入口添加可选重试
- **重试条件**：仅对可恢复错误重试（HTTP 429/5xx、网络超时），非业务逻辑错误

### 文件结构

| 文件 | 说明 |
|------|------|
| `retry.py` | 新增：重试/退避核心逻辑 |
| `app.py` | 修改：LLM API 调用处集成重试 |
| `ai_commands.py` | 修改：指令执行入口可选集成重试 |

### retry.py 设计

```python
import time
import random
import functools
from typing import Callable, Type

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # 秒
DEFAULT_MAX_DELAY = 30.0
DEFAULT_JITTER = 0.1  # ±10%


def exponential_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER
) -> float:
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay *= 1 + random.uniform(-jitter, jitter)
    return delay


def retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, OSError)
):
    """装饰器：自动重试被装饰函数"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = exponential_backoff(attempt, base_delay)
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


def retry_async(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, OSError)
):
    """异步版本装饰器"""
    # 实现细节，适用于 Flask SSE 流式场景
    pass
```

### app.py 集成

```python
from retry import retry

@retry(max_retries=3, base_delay=1.0)
def call_llm_stream(messages, ...):
    # 原有逻辑...
```

对于 SSE 流式场景（流中断后重试）：

```python
async def call_llm_stream_with_retry(messages, ...):
    for attempt in range(4):  # 初始 + 3次重试
        try:
            async for chunk in call_llm_stream(messages, ...):
                yield chunk
            break  # 成功完成
        except (ConnectionError, TimeoutError) as e:
            if attempt == 3:
                raise
            delay = exponential_backoff(attempt)
            await asyncio.sleep(delay)
```

## 任务分解

- [ ] 1. 创建 `retry.py` — 实现 `exponential_backoff()` 和同步 `retry` 装饰器
- [ ] 2. 实现 SSE 流式场景的异步重试逻辑
- [ ] 3. 修改 `app.py` — 在 LLM API 调用处集成重试
- [ ] 4. 修改 `ai_commands.py` — 在指令执行入口集成可选重试
- [ ] 5. 测试：模拟 API 临时故障验证重试行为
- [ ] 6. 提交 commit

## 关键决策

- **重试策略**：指数退避 + 10% 随机抖动，降低并发碰撞概率
- **可恢复错误**：仅 ConnectionError/TimeoutError/OSError（含 HTTP 429/5xx）
- **不可恢复错误**：业务逻辑错误（如指令语法错误）不重试
- **最大重试次数**：LLM 调用 3 次，指令执行 2 次
- **SSE 流式**：流中断从断点恢复较复杂，采用重新发送完整请求的策略
