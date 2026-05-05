"""
Skill 内容加载模块

提供 Skill 内容加载和 Gene slice 提取功能。
"""

import logging
import os
from pathlib import Path

import yaml

from ._cache import SkillContentCache
from ._types import SkillMetadata
from .skill_security import scan_for_injections, validate_path_within_dir, validate_skill_structure

logger = logging.getLogger(__name__)


def load_skill_content(
    name: str,
    skills_meta: dict[str, SkillMetadata],
    cache: SkillContentCache,
    fenced: bool = True,
) -> str | None:
    """加载完整 Skill 内容"""
    hit, cached_content = cache.get_cached(name)
    if hit:
        return cached_content

    if name not in skills_meta:
        return None

    skill_dir = Path(skills_meta[name]["dir"])
    skill_file = Path(skills_meta[name]["path"])

    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # 安全检查
    injection = scan_for_injections(content)
    if injection:
        return f"[Security Error] Skill '{name}' blocked: {injection}"

    symlink_check = validate_skill_structure(skill_dir)
    if symlink_check:
        return f"[Security Error] {symlink_check}"

    content = _expand_paths(content)
    fenced_content = f"<skill_content name='{name}'>\n{content}\n</skill_content>" if fenced else content
    cache.set(name, fenced_content)
    return fenced_content


def _expand_paths(content: str) -> str:
    """展开内容中的路径变量"""
    try:
        from src.shared_config import get_paths_config
        content = content.replace("~/.seed", str(get_paths_config().seed_base))
    except RuntimeError:
        pass
    return content.replace("~", os.path.expanduser("~"))


def get_gene_slice(name: str, skills_meta: dict[str, SkillMetadata]) -> str | None:
    """提取 Gene slice (Tier 2a): 核心控制信号"""
    if name not in skills_meta:
        return None

    skill_file = Path(skills_meta[name]["path"])
    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not content.startswith("---"):
        return _fallback_gene_slice(name, content)

    parts = content.split("---", 2)
    if len(parts) < 3:
        return _fallback_gene_slice(name, content)

    try:
        frontmatter = yaml.safe_load(parts[1].strip())
        return _build_gene_output(name, frontmatter) or _fallback_gene_slice(name, content)
    except yaml.YAMLError:
        return _fallback_gene_slice(name, content)


def _build_gene_output(name: str, fm: dict) -> str | None:
    """从 frontmatter 构建 Gene slice"""
    output = f"[SYSTEM: Skill '{name}' activated]\n\n"

    for section, key in [("Strategy", "strategy"), ("AVOID", "avoid"), ("Validation", "validation")]:
        if key in fm:
            output += f"## {section}\n" + "\n".join(f"- {item}" for item in fm[key]) + "\n\n"

    if "constraints" in fm:
        output += "## Constraints\n"
        c = fm["constraints"]
        if isinstance(c, dict):
            output += "\n".join(f"- {k}: {v}" for k, v in c.items()) + "\n"
        elif isinstance(c, list):
            output += "\n".join(f"- {item}" for item in c) + "\n"

    return output if len(output) > 50 else None


def _fallback_gene_slice(name: str, content: str) -> str:
    """生成 fallback Gene slice"""
    return f"[SYSTEM: Skill '{name}' activated]\n\n{content[:500]}"


def load_skill_ref(name: str, ref_path: str, skills_meta: dict[str, SkillMetadata]) -> str | None:
    """加载 skill 的参考文件（Tier 3）"""
    if name not in skills_meta:
        return None
    if ".." in ref_path:
        return "Error: Path traversal not allowed."

    skill_dir = Path(skills_meta[name]["dir"])
    target = (skill_dir / ref_path).resolve()
    if not validate_path_within_dir(target, skill_dir):
        return "Error: Path escapes skill directory."

    if not target.exists() or not target.is_file():
        return f"Reference file not found: {ref_path}"

    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"Error reading reference: {e}"


__all__ = [
    "load_skill_content",
    "get_gene_slice",
    "load_skill_ref",
]