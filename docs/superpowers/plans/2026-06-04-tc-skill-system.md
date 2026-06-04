# TC Skill System Enhancement Plan

> **机制编号：** 2.5 | **优先级：** P1 | **预估工时：** 3–4 天

## 目标

将 TC 现有的 ad-hoc `skills.md` 技能文件升级为结构化技能系统，支持技能发现、自动加载、去重合并和 URL 来源跟踪，让 Agent 能更有效地从经验和历史中学习。

## 背景

Opencode 的 `skill.ts` 定义了结构化技能格式（包含 frontmatter 元数据、描述、指令），`skill/discovery.ts` 支持技能发现（本地目录 + URL）。TC 当前在 `skills.md` 中有 11 条技能，格式为非结构化的自由文本，技能通过 system prompt 整体注入（`skills.md` 全部内容包含在 `_build_autonomous_system_prompt()` 中），无法按需加载或增量更新。

## 设计

### 核心思路

引入结构化技能格式，分离技能元数据和内容，支持按场景动态加载技能（而非每次注入全部技能）：

1. **结构化格式**：每个技能 YAML frontmatter + Markdown 内容
2. **技能注册表**：技能索引（名称 → 文件路径），支持目录扫描
3. **按需加载**：基于当前任务类型（测试/搭建/分析）仅加载相关技能
4. **自动去重合并**：新技能与现有技能相似度检测，合并而非追加

### 文件结构

| 文件 | 说明 |
|------|------|
| `turing_skills.py` | 新增：技能管理器核心逻辑 |
| `skills/` | 新增目录，存放结构化技能文件 |
| `skills.md` | 保留（向后兼容），改为自动生成的技能索引 |
| `app.py` | 修改：技能加载逻辑集成 |

### skills/ 目录结构

```
skills/
├── index.json              # 技能注册表（自动生成）
├── test-truth-table.md     # 真值表生成技能
├── debug-connection.md     # 电路查错技能
├── optimize-logic.md       # 逻辑化简技能
└── ...
```

单个技能文件格式：

```markdown
---
name: test-truth-table
description: 为电路生成所有输入组合的仿真真值表
tags: [testing, verification]
context: circuit-simulation
author: tc-agent
created: 2026-06-04
---

## Instructions

为当前电路生成真值表的步骤：
1. 获取电路所有 INPUT 元件列表
2. 生成 2^n 种输入组合
3. 对每种组合：SET 输入值 → SIM → SAMPLE 输出
4. 整理为表格格式输出
```

### turing_skills.py 设计

```python
import os
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Skill:
    id: str
    name: str
    description: str
    content: str
    tags: list[str] = field(default_factory=list)
    source_url: Optional[str] = None
    checksum: str = ""


class SkillManager:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self._index: dict[str, Skill] = {}
        self._load_index()

    def _load_index(self):
        """加载技能注册表"""
        index_path = os.path.join(self.skills_dir, "index.json")
        # ...

    def discover(self):
        """扫描 skills/ 目录发现新技能"""
        # ...

    def get_by_tags(self, tags: list[str]) -> list[Skill]:
        """按标签获取技能"""
        return [s for s in self._index.values() if any(t in s.tags for t in tags)]

    def merge_new(self, skill: Skill) -> bool:
        """合并新技能：checksum 去重，相似内容合并"""
        # ...

    def build_system_prompt_section(self, tags: list[str]) -> str:
        """为指定场景构建技能注入段"""
        skills = self.get_by_tags(tags)
        return "\n\n".join(f"## Skill: {s.name}\n{s.content}" for s in skills)
```

### app.py 集成

```python
from turing_skills import SkillManager

skill_mgr = SkillManager()

def _build_autonomous_system_prompt(task_type: str = None):
    # ...
    if task_type:
        skills_section = skill_mgr.build_system_prompt_section(tags_for_task(task_type))
    else:
        skills_section = skill_mgr.build_system_prompt_section(["general"])
    # ...
```

## 任务分解

- [ ] 1. 创建 `skills/` 目录和结构化技能格式规范文档
- [ ] 2. 迁移现有 skills.md 中 11 条技能到独立文件（YAML frontmatter + Markdown 内容）
- [ ] 3. 实现 `turing_skills.py` — `SkillManager._load_index()` 和 `discover()`
- [ ] 4. 实现按标签筛选技能加载 (`get_by_tags`)
- [ ] 5. 实现技能去重合并 (`merge_new`)
- [ ] 6. 修改 `_build_autonomous_system_prompt()` 按需加载技能
- [ ] 7. 测试：Agent 执行不同任务时正确加载不同技能
- [ ] 8. 提交 commit

## 关键决策

- **格式**：YAML frontmatter + Markdown（与 Opencode skill.ts 类似但更轻量）
- **去重策略**：基于 checksum（内容哈希）+ 名称相似度
- **标签系统**：使用 flat tags（无层级），方便按场景筛选
- **向后兼容**：保留 `skills.md` 作为自动生成的技能索引/概览
- **不做**URL 来源自动同步（TC 的技能全部自产，无需远程抓取）
