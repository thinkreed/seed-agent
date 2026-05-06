"""记忆写入辅助函数

路径映射和格式校验。
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_memory_root() -> Path:
    """获取记忆根目录（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "memory"


def _get_sessions_dir() -> Path:
    """获取会话目录"""
    return _get_memory_root() / "raw" / "sessions"


def _validate_skill_format(content: str, name: str = "") -> str:
    """校验 L2 Skill 格式是否符合 Open Agent Skills 规范

    Args:
        content: Skill 内容 (包含 YAML frontmatter)
        name: Skill 名称/文件名

    Returns:
        错误信息字符串，空字符串表示校验通过
    """
    # 校验 YAML frontmatter
    if not content.strip().startswith("---"):
        return "Error: L2 Skill must start with YAML frontmatter (---)."

    # 提取 frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "Error: L2 Skill must have closing --- for frontmatter."

    frontmatter_text = parts[1].strip()

    # 校验必需字段
    required_fields = ["name", "description"]
    for field in required_fields:
        if field not in frontmatter_text:
            return f"Error: L2 Skill frontmatter must contain '{field}' field."

    # 解析 name 字段
    name_match = re.search(r'name:\s*["\']?([^"\':\n]+)["\']?', frontmatter_text)
    if name_match:
        skill_name = name_match.group(1).strip()
        # name 校验规则：小写字母/数字/连字符，1-64字符
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", skill_name):
            return (
                f"Error: L2 Skill name '{skill_name}' must be lowercase "
                f"letters/numbers/hyphens, 1-64 chars, "
                f"no leading/trailing/consecutive hyphens."
            )
        if len(skill_name) > 64:
            return "Error: L2 Skill name exceeds 64 chars limit."

    # 校验 description 长度
    desc_match = re.search(
        r'description:\s*["\']?(.+?)["\']?\n', frontmatter_text, re.DOTALL
    )
    if desc_match:
        desc = desc_match.group(1).strip()
        if len(desc) > 1024:
            return "Error: L2 Skill description exceeds 1024 chars limit."
        if not desc:
            return "Error: L2 Skill description cannot be empty."

    # 校验文件名：必须是 skill_name/SKILL.md 格式
    if name:
        expected_name = f"{skill_name}/SKILL.md"
        if name not in (expected_name, "SKILL.md"):
            return f"Error: L2 filename must be '{expected_name}' (skill directory with SKILL.md)."

    return ""  # 校验通过


def _get_path(level: str, filename: str | None = None) -> str | None:
    """获取记忆文件路径

    Args:
        level: L1/L2/L3/L4
        filename: 文件名（L2-L4 需要）

    Returns:
        完整路径字符串，None 表示参数错误
    """
    mapping = {"L1": "notes.md", "L2": "skills", "L3": "knowledge", "L4": "raw"}
    if level not in mapping:
        return None
    base = mapping[level]
    memory_root = _get_memory_root()

    # L1 是单个文件，无需 filename
    if level == "L1":
        return os.path.join(memory_root, base)

    # L2-L4 需要指定 filename
    if not filename:
        return None

    # L2 特殊处理：skill 目录结构，自动补全 SKILL.md
    if level == "L2" and not filename.endswith("/SKILL.md") and filename != "SKILL.md":
        filename = os.path.join(filename, "SKILL.md")

    return os.path.join(memory_root, base, filename)


__all__ = [
    "_get_memory_root",
    "_get_sessions_dir",
    "_validate_skill_format",
    "_get_path",
]