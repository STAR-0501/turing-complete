"""Structured skill management system for Turing Complete circuit simulator.

Provides Skill dataclass with frontmatter parsing and a SkillManager
that manages a directory of structured skill files with index.json registry.
"""

import os
import json
import hashlib
import re
import logging
import threading
import glob
import time
from dataclasses import dataclass, field
from typing import Optional, List

from _common import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A reusable skill/knowledge entry with structured metadata."""

    id: str
    name: str
    description: str
    content: str
    tags: List[str] = field(default_factory=list)
    source_url: Optional[str] = None
    checksum: str = ""

    @staticmethod
    def from_markdown(filepath: str) -> 'Skill':
        """Parse a skill file with YAML-style frontmatter.

        Frontmatter between --- delimiters, content after.
        Fields: name, description, tags (comma-separated), author, created.
        Content is everything after the closing ---.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        return Skill._parse_text(text, filepath)

    @staticmethod
    def _parse_text(text: str, source: str = "") -> 'Skill':
        """Parse skill text with optional frontmatter."""
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

        # Strip the leading ### header line from content since it's redundant
        # with the frontmatter-derived name/id
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
        tags_str = ", ".join(self.tags)
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
        return Skill._compute_checksum(self.content)

    @staticmethod
    def _compute_checksum(content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


class SkillManager:
    """Manages structured skill files in a skills/ directory.

    Provides discovery, indexing, merging, and prompt section building.
    Thread-safe via threading.Lock.
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
        """Create skills/ directory if not exists."""
        os.makedirs(self._skills_abs_dir, exist_ok=True)

    def _index_path(self) -> str:
        return os.path.join(self._skills_abs_dir, "index.json")

    def _load_index(self):
        """Load index.json if it exists."""
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
        """Write index.json with current skill metadata."""
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
        atomic_write_json(idx_path, data)

    def _discover(self):
        """Scan skills/*.md for new/updated files, parse them, update _skills."""
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
        """Get a skill by id (case-insensitive)."""
        with self._lock:
            return self._skills.get(skill_id.lower())

    def list_all(self) -> List[Skill]:
        """Return all managed skills."""
        with self._lock:
            return list(self._skills.values())

    def get_by_tags(self, tags: Optional[List[str]] = None) -> List[Skill]:
        """Filter skills by tags. If tags is None/empty, returns all."""
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
        """Add or update a skill by checksum. Returns True if changed.

        If id matches existing and checksum matches, skip (no change).
        If id matches but checksum differs, update file and index.
        If new id, create new file and add to index.
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
        """Remove a skill by id. Returns True if removed."""
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
        """Re-scan skills/ directory. Public wrapper."""
        self._discover()
        self._save_index()

    @staticmethod
    def _infer_category(skill: Skill) -> str:
        """Infer category from skill id or tags."""
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
        """Format a skill id for display, e.g. 'skill-dbg-1' -> 'Skill-DBG-1',
        'cp-halfadder' -> 'CP-HalfAdder'."""
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
            # title-case join: half-adder -> Half-Adder, halfadder -> HalfAdder
            rest = rest.replace('-', ' ').title().replace(' ', '')
            return 'CP-' + rest
        return skill_id

    def build_prompt_section(self, tags: Optional[List[str]] = None) -> str:
        """Build a markdown section for injection into system prompt.

        If tags provided, filter to matching skills. Otherwise include all.
        Returns empty string if no skills match.
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
        """Regenerate the skills.md flat file as an auto-generated index.

        Preserves the file as backward-compatible reference for agents.
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
            "> Skills are distilled, general-purpose knowledge extracted from agent work sessions.",
            "> Each skill should be concise, abstract, and broadly applicable.",
            "> When you discover universal insight, add it here for future sessions.",
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
        lines.append("*To add a new skill: when you discover general-purpose knowledge during your work, append it above in this format and increment the total count.*")
        lines.append("*To add a new circuit pattern: document the build commands, verify cases, and reusable MODULE name.*")
        lines.append("")

        content = '\n'.join(lines)

        atomic_write_text(output_path, content)

    @staticmethod
    def parse_skills_block(text: str) -> List[Skill]:
        """Parse a <skills> block from agent response into Skill objects.

        Format expected:
            ## [Category]

            ### Skill-XXX-N: Title
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

            # Split by ### Skill- headers
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

                # Reconstruct full content with ### header prefix
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
        """Convert a category name to a list of tags."""
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
