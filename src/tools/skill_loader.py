"""Skill 加载器：遵循 Open Agent Skills 规范的渐进式加载"""

import os
import re
import yaml
from typing import List, Dict, Optional
from pathlib import Path

# Skills 目录路径
SKILLS_DIR = Path(os.path.expanduser("~")) / ".seed" / "memory" / "skills"


class SkillLoader:
    """Skill 加载器，支持渐进式披露"""

    def __init__(self, skills_dir: str = None):
        self.skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._skills_meta: Dict[str, Dict] = {}  # name -> metadata
        self._load_metadata()

    def _load_metadata(self):
        """启动时加载所有 skill 元数据（第一层披露）"""
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                meta = self._parse_frontmatter(skill_file)
                if meta:
                    self._skills_meta[meta['name']] = {
                        'path': str(skill_file),
                        'name': meta['name'],
                        'description': meta.get('description', ''),
                        'allowed_tools': meta.get('allowed-tools', ''),
                        'metadata': meta.get('metadata', {})
                    }
            except Exception:
                pass

    def _parse_frontmatter(self, skill_file: Path) -> Optional[Dict]:
        """解析 SKILL.md 的 YAML frontmatter"""
        with open(skill_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_text = parts[1].strip()
        try:
            return yaml.safe_load(frontmatter_text)
        except yaml.YAMLError:
            return None

    def get_skills_list(self) -> List[Dict]:
        """获取所有 skill 元数据列表"""
        return list(self._skills_meta.values())

    def get_skills_prompt(self) -> str:
        """生成注入到 system prompt 的 skill 列表"""
        if not self._skills_meta:
            return ""

        lines = ["## 可用技能 (Skills)", ""]
        for name, meta in self._skills_meta.items():
            desc = meta['description'][:200]  # 截断过长描述
            lines.append(f"- **{name}**: {desc}")

        lines.append("")
        lines.append("当用户请求匹配某技能描述时，可调用 `load_skill` 加载完整指令。")
        return "\n".join(lines)

    def match_skill(self, query: str) -> Optional[str]:
        """根据用户查询匹配最相关的 skill"""
        query_lower = query.lower()
        best_match = None
        best_score = 0

        for name, meta in self._skills_meta.items():
            # 检查 name 和 description 中的关键词
            keywords = [name.lower()] + meta['description'].lower().split()
            score = sum(1 for kw in keywords if kw in query_lower)

            if score > best_score:
                best_score = score
                best_match = name

        return best_match if best_score > 0 else None

    def load_skill_content(self, name: str) -> Optional[str]:
        """加载完整 skill 内容（第二层披露）"""
        if name not in self._skills_meta:
            return None

        skill_file = Path(self._skills_meta[name]['path'])
        if not skill_file.exists():
            return None

        with open(skill_file, 'r', encoding='utf-8') as f:
            return f.read()

    def get_skill_allowed_tools(self, name: str) -> List[str]:
        """获取 skill 预批准的工具列表"""
        if name not in self._skills_meta:
            return []

        allowed = self._skills_meta[name].get('allowed_tools', '')
        if isinstance(allowed, str):
            return allowed.split()
        elif isinstance(allowed, list):
            return allowed
        return []


def load_skill(name: str) -> str:
    """
    Load complete skill content by name.

    Args:
        name: Skill name (e.g., 'architecture-overview')

    Returns:
        Complete SKILL.md content or error message.
    """
    loader = SkillLoader()
    content = loader.load_skill_content(name)
    if content:
        return content
    return f"Skill not found: {name}. Available skills: {', '.join(loader._skills_meta.keys())}"


def list_skills() -> str:
    """
    List all available skills with descriptions.

    Returns:
        Formatted list of skills.
    """
    loader = SkillLoader()
    skills = loader.get_skills_list()

    if not skills:
        return "No skills available."

    output = "Available Skills:\n"
    for s in skills:
        output += f"- {s['name']}: {s['description'][:100]}...\n"

    return output


def register_skill_tools(registry):
    """Register skill tools."""
    registry.register("load_skill", load_skill)
    registry.register("list_skills", list_skills)