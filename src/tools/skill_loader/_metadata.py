"""
Skill 元数据解析模块

提供 Skill 元数据解析和加载功能。
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from ._matching import extract_desc_words
from ._types import SkillMeta

logger = logging.getLogger(__name__)


def parse_frontmatter(skill_file: Path) -> dict | None:
    """解析 YAML frontmatter

    Args:
        skill_file: Skill 文件路径

    Returns:
        解析后的 frontmatter 字典，失败返回 None
    """
    try:
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        return yaml.safe_load(parts[1].strip())
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None


def normalize_triggers(triggers: str | list[Any] | None) -> list[str]:
    """规范化 triggers

    Args:
        triggers: 触发词（字符串或列表）

    Returns:
        规范化后的触发词列表
    """
    if isinstance(triggers, str):
        return [t.strip() for t in triggers.split(",") if t.strip()]
    if isinstance(triggers, list):
        return _flatten_triggers(triggers)
    return []


def _flatten_triggers(triggers: list) -> list[str]:
    """扁平化嵌套列表

    Args:
        triggers: 嵌套触发词列表

    Returns:
        扁平化后的触发词列表
    """
    result = []
    for item in triggers:
        if isinstance(item, str):
            result.append(item.strip())
        elif isinstance(item, list):
            result.extend(_flatten_triggers(item))
    return result


def normalize_str_list(value: str | list | None) -> list[str]:
    """规范化字符串或列表

    Args:
        value: 字符串或列表

    Returns:
        规范化后的字符串列表
    """
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def parse_skill_meta(skill_file: Path, skill_dir: Path) -> SkillMeta | None:
    """解析单个 skill 元数据

    Args:
        skill_file: Skill 文件路径
        skill_dir: Skill 目录路径

    Returns:
        Skill 元数据，解析失败返回 None
    """
    try:
        parsed = parse_frontmatter(skill_file)
        if not parsed or "name" not in parsed:
            return None

        triggers = normalize_triggers(parsed.get("triggers", []))
        metadata = parsed.get("metadata", {}) or {}

        meta: SkillMeta = {
            "path": str(skill_file),
            "dir": str(skill_dir),
            "name": parsed["name"],
            "description": parsed.get("description", "")[:300],
            "category": parsed.get("category", "general"),
            "version": parsed.get("version", "1.0"),
            "triggers": triggers,
            "triggers_lower": {t.lower() for t in triggers},
            "platforms": normalize_str_list(parsed.get("platforms", [])),
            "allowed_tools": parsed.get("allowed-tools", ""),
            "requires_tools": normalize_str_list(metadata.get("requires_tools", [])),
            "fallback_for_tools": normalize_str_list(metadata.get("fallback_for_tools", [])),
            "desc_words": extract_desc_words(parsed.get("description", "")),
        }
        return meta
    except Exception as e:
        logger.debug(f"Failed to parse skill: {type(e).__name__}")
        return None


def convert_lists_to_sets(meta: dict) -> None:
    """将快照中的 list 转回 set

    Args:
        meta: 元数据字典（原地修改）
    """
    if "triggers_lower" in meta and isinstance(meta["triggers_lower"], list):
        meta["triggers_lower"] = set(meta["triggers_lower"])
    if "desc_words" in meta and isinstance(meta["desc_words"], list):
        meta["desc_words"] = set(meta["desc_words"])


__all__ = [
    "parse_frontmatter",
    "normalize_triggers",
    "normalize_str_list",
    "parse_skill_meta",
    "convert_lists_to_sets",
]