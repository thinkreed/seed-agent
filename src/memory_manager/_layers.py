"""层级访问模块

L1-L5 各层的访问方法
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_l1_index_content(l1_path: Path) -> str:
    """获取 L1 索引内容

    Args:
        l1_path: L1 索引文件路径

    Returns:
        索引内容字符串
    """
    if l1_path.exists():
        return l1_path.read_text(encoding="utf-8")
    return "L1 索引不存在"


def get_l2_skills_list(l2_path: Path) -> list[str]:
    """获取 L2 技能列表

    Args:
        l2_path: L2 技能目录路径

    Returns:
        技能名称列表
    """
    if l2_path.exists():
        skills: list[str] = []
        for skill_dir in l2_path.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skills.append(skill_dir.name)
        return skills
    return []


def get_l3_knowledge_list(l3_path: Path) -> list[str]:
    """获取 L3 知识列表

    Args:
        l3_path: L3 知识目录路径

    Returns:
        知识名称列表
    """
    if l3_path.exists():
        return [f.stem for f in l3_path.glob("*.md")]
    return []


def get_l4_user_profile_summary(user_modeling: Any) -> str:
    """获取 L4 用户画像摘要

    Args:
        user_modeling: UserModelingLayer 实例

    Returns:
        用户画像摘要字符串
    """
    return user_modeling.get_user_profile_summary()


def get_l5_archive_stats(archive: Any) -> dict[str, Any]:
    """获取 L5 归档统计

    Args:
        archive: LongTermArchiveLayer 实例

    Returns:
        归档统计字典
    """
    return archive.get_archive_stats()


def get_memory_hierarchy_summary(
    l1_path: Path,
    l2_path: Path,
    l3_path: Path,
    user_modeling: Any,
    archive: Any,
) -> str:
    """获取记忆层级摘要

    Args:
        l1_path: L1 索引路径
        l2_path: L2 技能路径
        l3_path: L3 知识路径
        user_modeling: UserModelingLayer 实例
        archive: LongTermArchiveLayer 实例

    Returns:
        层级摘要字符串
    """
    lines = ["=== 五层记忆架构摘要 ==="]

    # L1
    l1_exists = l1_path.exists()
    l1_size = 0
    if l1_exists:
        l1_size = len(l1_path.read_text(encoding="utf-8"))
    lines.append(f"L1 索引: {'存在' if l1_exists else '不存在'}, {l1_size} 字符")

    # L2
    l2_skills = get_l2_skills_list(l2_path)
    lines.append(f"L2 技能: {len(l2_skills)} 个技能")
    if l2_skills:
        lines.append(f"  - {', '.join(l2_skills[:5])}")

    # L3
    l3_knowledge = get_l3_knowledge_list(l3_path)
    lines.append(f"L3 知识: {len(l3_knowledge)} 条知识")
    if l3_knowledge:
        lines.append(f"  - {', '.join(l3_knowledge[:5])}")

    # L4
    l4_summary = get_l4_user_profile_summary(user_modeling)
    l4_prefs = user_modeling.get_all_preferences()
    lines.append(f"L4 用户画像: {len(l4_prefs)} 个偏好")
    if l4_prefs:
        lines.append(f"  {l4_summary[:200]}")

    # L5
    l5_stats = get_l5_archive_stats(archive)
    lines.append(
        f"L5 归档: {l5_stats['total_archives']} 个归档, "
        f"{l5_stats['total_events']} 个事件"
    )

    return chr(10).join(lines)