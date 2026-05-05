"""跨层搜索模块

搜索 L1-L5 各层内容
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def search_l1_index(l1_path: Path, keyword: str) -> list[dict[str, Any]]:
    """搜索 L1 索引

    Args:
        l1_path: L1 索引文件路径
        keyword: 搜索关键词

    Returns:
        搜索结果列表
    """
    if not l1_path.exists():
        return []

    content = l1_path.read_text(encoding="utf-8")
    keyword_lower = keyword.lower()

    if keyword_lower in content.lower():
        return [
            {
                "level": "L1",
                "source": "notes.md",
                "matched": True,
                "type": "index_entry",
            }
        ]
    return []


def search_l2_skills(
    l2_path: Path, keyword: str, limit: int
) -> list[dict[str, Any]]:
    """搜索 L2 技能

    Args:
        l2_path: L2 技能目录路径
        keyword: 搜索关键词
        limit: 结果限制

    Returns:
        搜索结果列表
    """
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
                    {
                        "level": "L2",
                        "source": skill_dir.name,
                        "matched": True,
                        "type": "skill",
                    }
                )
                if len(results) >= limit:
                    break
        except OSError:
            continue

    return results


def search_l3_knowledge(
    l3_path: Path, keyword: str, limit: int
) -> list[dict[str, Any]]:
    """搜索 L3 知识

    Args:
        l3_path: L3 知识目录路径
        keyword: 搜索关键词
        limit: 结果限制

    Returns:
        搜索结果列表
    """
    results: list[dict[str, Any]] = []
    if not l3_path.exists():
        return results

    keyword_lower = keyword.lower()

    for f in l3_path.glob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            if keyword_lower in content.lower():
                results.append(
                    {
                        "level": "L3",
                        "source": f.stem,
                        "matched": True,
                        "type": "knowledge",
                    }
                )
                if len(results) >= limit:
                    break
        except OSError:
            continue

    return results


def search_l4_user_preferences(
    user_modeling: Any, keyword: str
) -> list[dict[str, Any]]:
    """搜索 L4 用户画像

    Args:
        user_modeling: UserModelingLayer 实例
        keyword: 搜索关键词

    Returns:
        搜索结果列表
    """
    preferences = user_modeling.get_all_preferences()

    results: list[dict[str, Any]] = []
    keyword_lower = keyword.lower()

    for pref_key, pref_data in preferences.items():
        if keyword_lower in pref_key.lower():
            results.append(
                {
                    "level": "L4",
                    "source": pref_key,
                    "value": pref_data.get("usual"),
                    "type": "user_preference",
                }
            )

        usual = pref_data.get("usual", "")
        if usual and keyword_lower in usual.lower():
            results.append(
                {
                    "level": "L4",
                    "source": pref_key,
                    "value": usual,
                    "type": "user_preference",
                }
            )

    return results


def search_all_levels(
    l1_path: Path,
    l2_path: Path,
    l3_path: Path,
    user_modeling: Any,
    archive: Any,
    keyword: str,
    levels: list[str] | None = None,
    limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """跨层搜索

    Args:
        l1_path: L1 索引路径
        l2_path: L2 技能路径
        l3_path: L3 知识路径
        user_modeling: UserModelingLayer 实例
        archive: LongTermArchiveLayer 实例
        keyword: 搜索关键词
        levels: 搜索层级列表 (默认全部)
        limit: 每层结果限制

    Returns:
        各层搜索结果字典
    """
    if levels is None:
        levels = ["L1", "L2", "L3", "L4", "L5"]

    results: dict[str, list[dict[str, Any]]] = {}

    # L1 搜索
    if "L1" in levels:
        results["L1"] = search_l1_index(l1_path, keyword)

    # L2 搜索
    if "L2" in levels:
        results["L2"] = search_l2_skills(l2_path, keyword, limit)

    # L3 搜索
    if "L3" in levels:
        results["L3"] = search_l3_knowledge(l3_path, keyword, limit)

    # L4 用户画像搜索
    if "L4" in levels:
        results["L4"] = search_l4_user_preferences(user_modeling, keyword)

    # L5 归档搜索
    if "L5" in levels:
        results["L5"] = archive.search_with_context(keyword, limit)

    return results