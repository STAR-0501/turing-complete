"""上下文压实和溢出检测工具，用于 TC Agent 长对话管理。"""

import re


class OverflowDetector:
    """检测对话上下文是否接近 token 限制。"""

    def __init__(self, soft_limit: int = 32000, hard_limit: int = 48000):
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """基于字符数估算 token 数（中英文混合环境下 ≈ chars / 1.5）。"""
        return int(len(text) / 1.5)

    @staticmethod
    def count_messages_tokens(messages: list[dict]) -> int:
        """统计整个 messages 列表的估算 token 数。"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += OverflowDetector.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += OverflowDetector.estimate_tokens(block["text"])
        return total

    def should_compact(self, messages: list[dict]) -> bool:
        """超过软限制即需要压实。"""
        return self.count_messages_tokens(messages) > self.soft_limit

    def is_overflow(self, messages: list[dict]) -> bool:
        """超过硬限制即溢出。"""
        return self.count_messages_tokens(messages) > self.hard_limit


class ContextCompactor:
    """将历史对话压实为结构化摘要，保留最新若干轮完整交互。"""

    # 需要从历史提取的关键电路信息
    _STATE_PATTERNS = [
        r"(?:电路|circuit).{0,20}(?:包含|包含|有|has|contain).+",
        r"(?:添加|ADD|add).+",
        r"(?:连接|WIRE|wire|连线).+",
        r"(?:模块|module|MODULE).+",
        r"(?:元件|element|gate|门).+",
        r"(?:真值表|truth|仿真|sim|SIM|simulate).+",
        r"(?:done|完成|待办|todo).+",
        r"(?:错误|error|失败|fail).+",
    ]

    def __init__(self, keep_rounds: int = 2):
        self.keep_rounds = keep_rounds

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        压实策略：

        1. 保留系统 prompt（index 0）
        2. 保留最后 N 轮完整对话（user + assistant 对）
        3. 将中间历史压实为一条带摘要的 system 消息
        """
        if len(messages) < 4:
            return messages

        system = messages[0]
        total_rounds = (len(messages) - 1) // 2
        keep_rounds = min(self.keep_rounds, total_rounds - 1)

        # 最后 N 轮保留
        keep_count = keep_rounds * 2
        recent = messages[-keep_count:] if keep_count > 0 else messages[1:]

        # 中间历史进行压实
        history_msgs = messages[1:-keep_count] if keep_count > 0 else []

        if not history_msgs:
            return [system] + recent

        summary = self._summarize_history(history_msgs)

        compacted = [
            system,
            {
                "role": "system",
                "content": f"【历史摘要】以下是对之前对话的压实总结：\n{summary}\n\n"
                           f"（上述内容已替代先前 {len(history_msgs)} 条消息的详细记录。）"
            }
        ] + recent

        return compacted

    def _summarize_history(self, messages: list[dict]) -> str:
        """从历史消息中提取电路结构、已完成操作和当前任务状态。"""
        circuit_lines = []
        done_lines = []
        error_lines = []

        for i, msg in enumerate(messages):
            content = msg.get("content", "") or ""

            if isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict)]
                content = "\n".join(texts)

            if not isinstance(content, str):
                continue

            role = msg.get("role", "unknown")
            prefix = "AI" if role == "assistant" else "用户"

            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if any(re.search(p, line, re.IGNORECASE) for p in self._STATE_PATTERNS):
                    circuit_lines.append(f"  [{prefix}] {line[:200]}")
                if re.search(r"(?:done|完成|true)", line, re.IGNORECASE):
                    done_lines.append(f"  [{prefix}] {line[:200]}")
                if re.search(r"(?:错误|error|失败|fail|warning)", line, re.IGNORECASE):
                    error_lines.append(f"  [{prefix}] {line[:200]}")

        parts = []

        if circuit_lines:
            parts.append("### 电路状态变化\n" + "\n".join(circuit_lines[:20]))

        if done_lines:
            parts.append("### 任务完成状态\n" + "\n".join(done_lines[:10]))

        if error_lines:
            parts.append("### 错误/警告\n" + "\n".join(error_lines[:10]))

        round_count = len(messages) // 2
        parts.insert(0, f"共 {round_count} 轮交互。")

        return "\n\n".join(parts)
