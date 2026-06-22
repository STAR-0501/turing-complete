"""Turing Complete 电路模拟器的结构化技能管理系统。

提供带 frontmatter 解析的 Skill 数据类和 SkillManager，
管理结构化技能文件目录和 index.json 注册表。
"""

import os
import json
import hashlib
import re
import logging
import threading
import glob
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """一个带有结构化元数据的可复用技能/知识条目。"""

    id: str
    name: str
    description: str
    content: str
    tags: List[str] = field(default_factory=list)
    source_url: Optional[str] = None
    checksum: str = ""

    @staticmethod
    def from_markdown(filepath: str) -> 'Skill':
        """解析带有 YAML 风格 frontmatter 的技能文件。

        --- 分隔符之间的元数据，之后是内容。
        字段: name, description, tags（逗号分隔）, author, created。
        内容是结束 --- 之后的所有内容。
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        return Skill._parse_text(text, filepath)

    @staticmethod
    def _parse_text(text: str, source: str = "") -> 'Skill':
        """解析带可选 frontmatter 的技能文本。"""
        frontmatter = {}
        body = text

        if text.startswith('---'):
            parts = text.split('---', 2)
            if len(parts) >= 3 and parts[0] == '':
                fm_text = parts[1].strip()
                body = parts[2].strip()
                for line in fm_text.split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, _, value = line.partition(':')
                        key = key.strip().lower()
                        value = value.strip().strip('"').strip("'")
                        frontmatter[key] = value

        name = frontmatter.get('name', '')
        description = frontmatter.get('description', '')

        tags_str = frontmatter.get('tags', '')
        tags_str = tags_str.strip('[]').strip('"').strip("'")
        tags = [
            t.strip().strip('"').strip("'")
            for t in tags_str.split(',')
            if t.strip()
        ]

        skill_id = frontmatter.get('id', '')
        if not skill_id:
            id_match = re.search(r'###\s+(Skill-[\w-]+)', body)
            if id_match:
                skill_id = id_match.group(1).lower()

        # 从内容中移除前导的 ### 标题行，因为它与 frontmatter 派生的名称/ID 重复
        content = body
        content_lines = content.split('\n', 1)
        if content_lines and re.match(r'^###\s+(Skill-[\w-]+|CP-[\w-]+)', content_lines[0]):
            content = content_lines[1].strip() if len(content_lines) > 1 else ""
        checksum = Skill._compute_checksum(body)

        return Skill(
            id=skill_id,
            name=name,
            description=description,
            content=content,
            tags=tags,
            checksum=checksum,
        )

    def to_markdown(self) -> str:
        """Serialize back to frontmatter + content format."""
        tag序列化回 frontmatter + 内容格式。
        lines = ['---']
        if self.id:
            lines.append(f'id: {self.id}')
        if self.name:
            lines.append(f'name: {self.name}')
        if self.description:
            lines.append(f'description: {self.description}')
        if tags_str:
            lines.append(f'tags: [{tags_str}]')
        lines.append('---')
        lines.append('')
        lines.append(self.content)
        return '\n'.join(lines)

    def compute_checksum(self) -> str:
        """SHA-256 of normalized content."""
        ret返回规范化内容的 SHA-256。lf.content)

    @staticmethod
    def _compute_checksum(content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


class SkillManager:
    """管理 skills/ 目录中的结构化技能文件。

    提供发现、索引、合并和提示词段落构建功能。
    通过 threading.Lock 保证线程安全。
    """

    def __init__(self, skills_dir: str = "skills", base_dir: Optional[str] = None):
        self.skills_dir = skills_dir
        self._base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        if not os.path.isabs(self.skills_dir):
            self._skills_abs_dir = os.path.join(self._base_dir, self.skills_dir)
        else:
            self._skills_abs_dir = self.skills_dir
        self._skills: dict[str, Skill] = {}
        self._lock = threading.Lock()
        self._ensure_dir()
        self._load_index()
        self._discover()
        self._save_index()

    def _ensure_dir(self):
        """如果 skills/ 目录不存在则创建。"""
        os.makedirs(self._skills_abs_dir, exist_ok=True)

    def _index_path(self) -> str:
        return os.path.join(self._skills_abs_dir, "index.json")

    def _load_index(self):
        """如果存在则加载 index.json。"""
        idx_path = self._index_path()
        if os.path.exists(idx_path):
            try:
                with open(idx_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._skills = {}
                    for skill_id, meta in data.items():
                        self._skills[skill_id] = Skill(
                            id=meta.get('id', skill_id),
                            name=meta.get('name', ''),
                            description=meta.get('description', ''),
                            content=meta.get('content', ''),
                            tags=meta.get('tags', []),
                            source_url=meta.get('source_url'),
                            checksum=meta.get('checksum', ''),
                        )
            except Exception as e:
                logger.warning("Failed to load skill index: %s", e)

    def _save_index(self):
        """用当前技能元数据写入 index.json。"""
        idx_path = self._index_path()
        data = {}
        for skill_id, skill in self._skills.items():
            data[skill_id] = {
                'id': skill.id,
                'name': skill.name,
                'description': skill.description,
                'content': skill.content,
                'tags': list(skill.tags),
                'source_url': skill.source_url,
                'checksum': skill.checksum,
            }
        dir_name = os.path.dirname(idx_path) or os.getcwd()
        tmp = os.path.join(dir_name, f".index.json.tmp.{os.getpid()}")
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, idx_path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def _discover(self):
        """扫描 skills/*.md 查找新/更新的文件，解析并更新 _skills。"""
        pattern = os.path.join(self._skills_abs_dir, "*.md")
        for filepath in glob.glob(pattern):
            basename = os.path.basename(filepath)
            if basename.lower() in ('index.md',):
                continue
            try:
                skill = Skill.from_markdown(filepath)
                if not skill.id:
                    logger.warning(
                        "Skill file %s has no id, skipping", filepath)
                    continue
                with self._lock:
                    existing = self._skills.get(skill.id)
                    if not existing or existing.checksum != skill.checksum:
                        self._skills[skill.id] = skill
            except Exception as e:
                logger.warning(
                    "Failed to parse skill file %s: %s", filepath, e)

    def get(self, skill_id: str) -> Optional[Skill]:
        """按 id 获取技能（不区分大小写）。"""
        with self._lock:
            return self._skills.get(skill_id.lower())

    def list_all(self) -> List[Skill]:
        """返回所有管理的技能。"""
        with self._lock:
            return list(self._skills.values())

    def get_by_tags(self, tags: Optional[List[str]] = None) -> List[Skill]:
        """按标签过滤技能。如果 tags 为 None/空，返回全部。"""
        if not tags:
            return self.list_all()
        tags_lower = [t.lower().strip() for t in tags if t.strip()]
        if not tags_lower:
            return self.list_all()
        with self._lock:
            return [
                s for s in self._skills.values()
                if any(t.lower() in tags_lower for t in s.tags)
            ]

    def merge(self, skill: Skill) -> bool:
        """按校验和添加或更新技能。如果变化返回 True。

        如果同一 id 的技能已存在且校验和匹配：跳过（无变化）。
        如果同一 id 但校验和不同：更新文件和索引。
        如果是新 id：创建新文件并添加到索引。
        """
        with self._lock:
            existing = self._skills.get(skill.id)
            if existing and existing.checksum == skill.checksum:
                return False

            filename = skill.id + ".md" if skill.id else f"unnamed_{len(self._skills)}.md"
            filepath = os.path.join(self._skills_abs_dir, filename)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(skill.to_markdown())
            except Exception as e:
                logger.error(
                    "Failed to write skill file %s: %s", filepath, e)
                return False

            self._skills[skill.id] = skill
            self._save_index()
            return True

    def remove(self, skill_id: str) -> bool:
        """按 id 移除技能。如果移除成功返回 True。"""
        with self._lock:
            if skill_id not in self._skills:
                return False
            del self._skills[skill_id]
            filepath = os.path.join(self._skills_abs_dir, skill_id + ".md")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            self._save_index()
            return True

    def discover(self):
        """重新扫描 skills/ 目录。公共包装方法。"""
        self._discover()
        self._save_index()

    @staticmethod
    def _infer_category(skill: Skill) -> str:
        """从技能 id 或标签推断分类。"""
        id_lower = skill.id.lower()
        for prefix, cat in [
            ('skill-dbg', 'Debugging'),
            ('dbg', 'Debugging'),
            ('skill-arch', 'Architecture'),
            ('arch', 'Architecture'),
            ('skill-fe', 'Frontend'),
            ('fe', 'Frontend'),
            ('skill-be', 'Backend'),
            ('be', 'Backend'),
            ('skill-cp', 'Circuit Patterns'),
            ('cp', 'Circuit Patterns'),
        ]:
            if id_lower.startswith(prefix):
                return cat

        tag_map = {
            'debugging': 'Debugging',
            'debug': 'Debugging',
            'architecture': 'Architecture',
            'frontend': 'Frontend',
            'backend': 'Backend',
            'circuit': 'Circuit Patterns',
            'pattern': 'Circuit Patterns',
        }
        for tag in skill.tags:
            tl = tag.lower()
            if tl in tag_map:
                return tag_map[tl]

        return 'Uncategorized'

    @staticmethod
    def _format_skill_id(skill_id: str) -> str:
        """格式化技能 id 用于显示，例如 'skill-dbg-1' -> 'Skill-DBG-1',
        'cp-halfadder' -> 'CP-HalfAdder'。"""
        parts = skill_id.split('-')
        if not parts:
            return skill_id

        prefix = parts[0].lower()
        if prefix == 'skill':
            # skill-dbg-1 -> Skill-DBG-1
            out = 'Skill'
            for p in parts[1:-1]:
                out += '-' + p.upper()
            if len(parts) > 1:
                out += '-' + parts[-1].upper()
            return out
        elif prefix == 'cp':
            # cp-halfadder -> CP-HalfAdder
            rest = '-'.join(parts[1:])
            # 标题大小写连接: half-adder -> Half-Adder, halfadder -> HalfAdder
            rest = rest.replace('-', ' ').title().replace(' ', '')
            return 'CP-' + rest
        return skill_id

    def build_prompt_section(self, tags: Optional[List[str]] = None) -> str:
        """构建用于注入系统提示词的 markdown 段落。

        如果提供了标签，过滤出匹配的技能。否则包含所有技能。
        如果没有匹配的技能则返回空字符串。
        """
        skills = self.get_by_tags(tags)
        if not skills:
            return ""

        lines = ["--- 累计经验技能 ---", ""]
        for skill in skills:
            skill_label = SkillManager._format_skill_id(skill.id)
            lines.append(f"### {skill_label}: {skill.name}")
            if skill.description:
                lines.append(f"- **描述**: {skill.description}")
            if skill.tags:
                lines.append(f"- **标签**: {', '.join(skill.tags)}")
            lines.append("")
            if skill.content:
                lines.append(skill.content)
                lines.append("")

        return "\n".join(lines).strip()

    def regenerate_index_md(self, output_path: str):
        """重新生成 skills.md 平面文件作为自动生成的索引。

        保持文件作为代理的向后兼容参考。
        """
        with self._lock:
            skills = list(self._skills.values())

        categories: dict[str, list] = {}
        for skill in skills:
            cat = SkillManager._infer_category(skill)
            categories.setdefault(cat, []).append(skill)

        today = time.strftime('%Y-%m-%d')
        lines = [
            "# Agent Skills (Self-Evolving Knowledge Base)",
            "",
            f"_Last updated: {today}_",
            f"_Total skills: {len(skills)}_",
            "",
            "> 技能是从代理工作会话中提取的提炼后的通用知识。",
            "> 每个技能应简洁、抽象且广泛适用。",
            "> 当你发现通用洞见时，将其添加至此以供未来会话使用。",
            "",
        ]

        cat_order = [
            "Debugging",
            "Architecture",
            "Frontend",
            "Backend",
            "Circuit Patterns",
            "Uncategorized",
        ]
        sorted_cats = sorted(
            categories.keys(),
            key=lambda c: cat_order.index(c) if c in cat_order else 99,
        )

        for cat in sorted_cats:
            cat_skills = categories[cat]
            lines.append("---")
            lines.append("")
            lines.append(f"## {cat}")
            lines.append("")
            for skill in cat_skills:
                skill_label = SkillManager._format_skill_id(skill.id)
                lines.append(f"### {skill_label}: {skill.name}")
                if skill.content:
                    lines.append(skill.content)
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*添加新技能：当你在工作中发现通用知识时，按此格式追加到上方并增加总数。*")
        lines.append("*添加新电路模式：记录构建命令、验证用例和可复用的模块名称。*")
        lines.append("")

        content = '\n'.join(lines)

        dir_name = os.path.dirname(output_path) or os.getcwd()
        for stale in glob.glob(
            os.path.join(dir_name, f".{os.path.basename(output_path)}.tmp.*")
        ):
            try:
                os.remove(stale)
            except OSError:
                pass
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=dir_name,
            prefix=f".{os.path.basename(output_path)}.tmp.",
            delete=False
        ) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
            tmp_path = f.name
        try:
            os.replace(tmp_path, output_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def parse_skills_block(text: str) -> List[Skill]:
        """将代理响应中的 <skills> 块解析为 Skill 对象。

        预期格式:
            ## [类别]

            ### Skill-XXX-N: 标题
            - **Context**: ...
            - **What**: ...
            - **Why**: ...
            - **Example**: ...
        """
        skills = []
        sections = re.split(r'^##\s+', text, flags=re.MULTILINE)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            cat_lines = section.split('\n', 1)
            category = cat_lines[0].strip()
            body = cat_lines[1] if len(cat_lines) > 1 else ''

            # 按 ### Skill- 标题分割
            skill_blocks = re.split(
                r'^###\s+(?=Skill-[\w-]+:)', body, flags=re.MULTILINE)
            for block in skill_blocks:
                block = block.strip()
                if not block:
                    continue

                header_line = block.split('\n')[0].strip()
                h_match = re.match(
                    r'(Skill-[\w-]+):\s*(.*)', header_line)
                if not h_match:
                    continue
                skill_id = h_match.group(1).lower()
                skill_name = h_match.group(2).strip()

                # 使用 ### 标题前缀重建完整内容
                content = '### ' + header_line
                rest_lines = block.split('\n')[1:]
                if rest_lines:
                    content += '\n' + '\n'.join(rest_lines)

                desc = ''
                desc_match = re.search(
                    r'\*\*Context\*\*:\s*(.*)', content)
                if desc_match:
                    desc = desc_match.group(1).strip()

                tags = SkillManager._category_to_tags(category)

                checksum = Skill._compute_checksum(content)
                skills.append(Skill(
                    id=skill_id,
                    name=skill_name,
                    description=desc,
                    content=content,
                    tags=tags,
                    checksum=checksum,
                ))

        return skills

    @staticmethod
    def _category_to_tags(category: str) -> List[str]:
        """将分类名称转换为标签列表。"""
        cat_lower = category.lower().strip()
        if 'debug' in cat_lower:
            return ['debugging', 'windows']
        elif 'arch' in cat_lower:
            return ['architecture']
        elif 'frontend' in cat_lower or cat_lower in ('fe',):
            return ['frontend']
        elif 'backend' in cat_lower or cat_lower in ('be',):
            return ['backend']
        elif 'circuit' in cat_lower:
            return ['circuit', 'pattern']
        return []
