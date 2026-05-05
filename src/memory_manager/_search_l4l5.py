"""L4-L5 层搜索模块

搜索数据库层（用户画像、归档）
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def search_l4_user_preferences(user_modeling: Any, keyword: str) -> list[dict[str, Any]]:
    """搜索 L4 用户画像"""
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
    l1_path: Any,
    l2_path: Any,
    l3_path: Any,
    user_modeling: Any,
    archive: Any,
    keyword: str,
    levels: list[str] | None = None,
    limit: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """跨层搜索"""
    from ._search_l1l3 import search_l1_index, search_l2_skills, search_l3_knowledge

    if levels is None:
        levels = ["L1", "L2", "L3", "L4", "L5"]

    results: dict[str, list[dict[str, Any]]] = {}

    if "L1" in levels:
        results["L1"] = search_l1_index(l1_path, keyword)

    if "L2" in levels:
        results["L2"] = search_l2_skills(l2_path, keyword, limit)

    if "L3" in levels:
        results["L3"] = search_l3_knowledge(l3_path, keyword, limit)

    if "L4" in levels:
        results["L4"] = search_l4_user_preferences(user_modeling, keyword)

    if "L5" in levels:
        results["L5"] = archive.search_with_context(keyword, limit)

    return results