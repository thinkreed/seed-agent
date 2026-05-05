"""L1-L3 层搜索模块

搜索文件系统层（索引、技能、知识）
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def search_l1_index(l1_path: Path, keyword: str) -> list[dict[str, Any]]:
    """搜索 L1 索引"""
    if not l1_path.exists():
        return []

    content = l1_path.read_text(encoding="utf-8")
    keyword_lower = keyword.lower()

    if keyword_lower in content.lower():
        return [
            {"level": "L1", "source": "notes.md", "matched": True, "type": "index_entry"}
        ]
    return []


def search_l2_skills(l2_path: Path, keyword: str, limit: int) -> list[dict[str, Any]]:
    """搜索 L2 技能"""
    results: list[dict[str, Any]] = []
    if not l2_path.exists():
        return results

    keyword_lower = keyword.lower()

    for skill_dir in l2_path.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            if keyword_lower in content.lower():
                results.append(
                    {"level": "L2", "source": skill_dir.name, "matched": True, "type": "skill"}
                )
                if len(results) >= limit:
                    break
        except OSError:
            continue

    return results


def search_l3_knowledge(l3_path: Path, keyword: str, limit: int) -> list[dict[str, Any]]:
    """搜索 L3 知识"""
    results: list[dict[str, Any]] = []
    if not l3_path.exists():
        return results

    keyword_lower = keyword.lower()

    for f in l3_path.glob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            if keyword_lower in content.lower():
                results.append(
                    {"level": "L3", "source": f.stem, "matched": True, "type": "knowledge"}
                )
                if len(results) >= limit:
                    break
        except OSError:
            continue

    return results