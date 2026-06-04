"""
Dynamic instruction injection system for Turing Complete.
Organizes AI instructions by task scenario for focused system prompts.
"""

import re
import os
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class InstructionGroup:
    """A group of instructions belonging to one scenario."""
    id: str
    name: str
    content: str
    scenario: str  # "always" | "test" | "debug" | "module" | "optimize"
    priority: int = 0


class InstructionManager:
    """Loads AI_INSTRUCTIONS.md and builds scenario-focused prompt sections.

    Parses %%SCENARIO:xxx%% markers in the markdown file to group instructions
    by scenario. The same scenario can appear multiple times (content accumulates).
    Content before the first marker defaults to "always".
    """

    def __init__(self, base_file: str = "AI_INSTRUCTIONS.md"):
        self.base_file = base_file
        self._groups: dict[str, InstructionGroup] = {}
        self._error: Optional[str] = None
        self._load()

    def _load(self):
        """Parse %%SCENARIO:xxx%% markers from the markdown file."""
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
            # No markers at all — everything belongs to "always"
            text = parts[0].strip()
            if text:
                accumulated["always"] = text
        else:
            # First element is content before first marker
            first = parts[0].strip()
            if first:
                accumulated["always"] = first

            # Remaining: alternating [scenario_name, content, ...]
            for i in range(1, len(parts) - 1, 2):
                scenario = parts[i]
                scenario_content = parts[i + 1] if i + 1 < len(parts) else ""
                if scenario not in accumulated:
                    accumulated[scenario] = ""
                accumulated[scenario] += '\n' + scenario_content.strip()

        # Build InstructionGroup objects
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
        """Build a scenario-focused instruction highlight section.

        1. Always-group instructions (always injected first)
        2. Active scenario instructions (highlighted with section header)
        3. Other scenario instructions (brief reference appendix)

        Args:
            scenarios: List of active scenario names (e.g. ["test", "debug"]).
                       None or empty list means only "always" group is shown.
        """
        if scenarios is None:
            scenarios = []

        sections = []

        # 1. Always group (base commands — always present)
        if "always" in self._groups:
            sections.append(self._groups["always"].content)

        # 2. Active scenario groups sorted by priority DESC
        active = [
            g for s in scenarios
            for g in [self._groups.get(s)]
            if g is not None and g.scenario != "always"
        ]
        # Deduplicate by id while preserving order
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

        # 3. Other scenario groups as brief reference
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
        """Map circuit mode + user message keywords to active scenario list.

        Args:
            mode: "circuit" or "chat" (from _quick_classify).
            message: The current user message for keyword matching.

        Returns:
            List of scenario names matching the current task context.
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
        """Return all scenario names except 'always'."""
        return list(set(
            g.scenario for g in self._groups.values() if g.scenario != "always"
        ))

    @property
    def error(self) -> Optional[str]:
        """Return load error message, if any."""
        return self._error
