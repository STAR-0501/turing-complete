"""
Turing Complete 动态指令注入系统。
按任务场景组织 AI 指令，实现聚焦的系统提示词。
"""

import re
import os
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class InstructionGroup:
    """属于一个场景的一组指令。"""
    id: str
    name: str
    content: str
    scenario: str  # "always" | "test" | "debug" | "module" | "optimize"
    priority: int = 0


class InstructionManager:
    """加载 AI_INSTRUCTIONS.md 并构建按场景聚焦的提示词段落。

    解析 markdown 文件中的 %%SCENARIO:xxx%% 标记，按场景分组指令。
    同一场景可以出现多次（内容会累积）。
    第一个标记之前的内容默认为 "always"。
    """

    def __init__(self, base_file: str = "AI_INSTRUCTIONS.md"):
        self.base_file = base_file
        self._groups: dict[str, InstructionGroup] = {}
        self._error: Optional[str] = None
        self._load()

    def _load(self):
        """从 markdown 文件中解析 %%SCENARIO:xxx%% 标记。"""
        content = ""
        try:
            with open(self.base_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (FileNotFoundError, OSError) as e:
            self._error = str(e)
            return

        pattern = r'%%SCENARIO:(\w+)%%'
        parts = re.split(pattern, content)
        accumulated: dict[str, str] = {}

        if len(parts) == 1:
            # 没有标记——所有内容属于 "always"
            text = parts[0].strip()
            if text:
                accumulated["always"] = text
        else:
            # 第一个元素是第一个标记之前的内容
            first = parts[0].strip()
            if first:
                accumulated["always"] = first

            # 剩余部分：交替 [场景名称, 内容, ...]
            for i in range(1, len(parts) - 1, 2):
                scenario = parts[i]
                scenario_content = parts[i + 1] if i + 1 < len(parts) else ""
                if scenario not in accumulated:
                    accumulated[scenario] = ""
                accumulated[scenario] += '\n' + scenario_content.strip()

        # 构建 InstructionGroup 对象
        priority_map = {
            "always": 100,
            "test": 80,
            "debug": 70,
            "module": 60,
            "optimize": 50,
        }
        for scenario, group_content in accumulated.items():
            clean = group_content.strip()
            if clean:
                self._groups[scenario] = InstructionGroup(
                    id=f"scenario_{scenario}",
                    name=f"Scenario: {scenario}",
                    content=clean,
                    scenario=scenario,
                    priority=priority_map.get(scenario, 0),
                )

    def build_prompt_section(self, scenarios: Optional[List[str]] = None) -> str:
        """构建按场景聚焦的指令突出显示段落。

        1. Always 组指令（总是首先注入）
        2. 当前活跃场景指令（用段落标题突出显示）
        3. 其他场景指令（简短的参考附录）

        参数:
            scenarios: 活跃场景名称列表（例如 ["test", "debug"]）。
                       None 或空列表表示只显示 "always" 组。
        """
        if scenarios is None:
            scenarios = []

        sections = []

        # 1. Always 组（基础指令——始终存在）
        if "always" in self._groups:
            sections.append(self._groups["always"].content)

        # 2. 活跃场景组，按优先级降序排列
        active = [
            g for s in scenarios
            for g in [self._groups.get(s)]
            if g is not None and g.scenario != "always"
        ]
        # 按 id 去重，同时保持顺序
        seen = set()
        unique_active = []
        for g in active:
            if g.id not in seen:
                seen.add(g.id)
                unique_active.append(g)
        unique_active.sort(key=lambda g: g.priority, reverse=True)

        for g in unique_active:
            header = f"\n=== 当前场景：{g.name.replace('Scenario: ', '')} ===\n"
            sections.append(header + g.content)

        # 3. 其他场景组作为简要参考
        remaining = [
            g for g in self._groups.values()
            if g.scenario != "always" and g.scenario not in scenarios
        ]
        if remaining:
            ref_lines = ["\n=== 其他场景指令（参考） ==="]
            for g in remaining:
                first_line = g.content.split('\n')[0].strip().lstrip('#').strip()
                label = g.name.replace('Scenario: ', '')
                ref_lines.append(f"• {label}: {first_line}")
            sections.append("\n".join(ref_lines))

        return "\n\n".join(s for s in sections if s)

    def resolve_scenario_from_mode(self, mode: str, message: str = "") -> List[str]:
        """将电路模式 + 用户消息关键词映射到活跃场景列表。

        参数:
            mode: "circuit" 或 "chat"（来自 _quick_classify）。
            message: 用于关键词匹配的当前用户消息。

        返回:
            匹配当前任务上下文的场景名称列表。
        """
        if mode != "circuit":
            return []

        msg = message.lower()
        found: set[str] = set()

        test_keywords = [
            "测试", "仿真", "验证", "test", "truth", "真值",
            "verify", "真值表", "sample", "sim", "仿真",
        ]
        debug_keywords = [
            "查错", "检查", "错误", "问题", "debug", "bug",
            "故障", "异常", "出错", "不对", "不工作", "wrong",
            "不运行", "信号", "电平",
        ]
        module_keywords = [
            "模块", "封装", "打包", "module", "define",
            "定义", "func", "function", "自定义", "子电路",
        ]
        optimize_keywords = [
            "优化", "化简", "简化", "减少", "optimize",
            "冗余", "精简", "improve", "gate", "门数",
        ]

        if any(k in msg for k in test_keywords):
            found.add("test")
        if any(k in msg for k in debug_keywords):
            found.add("debug")
        if any(k in msg for k in module_keywords):
            found.add("module")
        if any(k in msg for k in optimize_keywords):
            found.add("optimize")

        return list(found)

    def list_scenarios(self) -> List[str]:
        """返回除 'always' 之外的所有场景名称。"""
        return list(set(
            g.scenario for g in self._groups.values() if g.scenario != "always"
        ))

    @property
    def error(self) -> Optional[str]:
        """返回加载错误信息（如果有）。"""
        return self._error
