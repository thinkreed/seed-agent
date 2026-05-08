"""
缓存数据转换模块 - set/list 类型互转

用于 JSON 序列化兼容和内存 O(1) 查找优化。
"""

from typing import Any


def convert_lists_to_sets(skills_meta: dict) -> dict:
    """
    将 skills_meta 中的特定字段从 list 转换回 set

    用于加载快照后恢复内存中的 set 类型（支持 O(1) 查找）。

    Args:
        skills_meta: 从 JSON 加载的技能元数据

    Returns:
        包含 set 类型字段的元数据
    """
    set_fields = {"triggers_lower", "desc_words"}  # 需要转为 set 的字段名

    for meta in skills_meta.values():
        for field in set_fields:
            if field in meta and isinstance(meta[field], list):
                meta[field] = set(meta[field])

    return skills_meta


def convert_sets_to_lists(obj: dict | list | set | Any) -> dict | list | Any:
    """
    递归转换 dict 中的 set 为 list（JSON 序列化兼容）

    自动将 set 类型字段转换为 list 以支持 JSON 序列化。

    Args:
        obj: 待转换的对象（dict、list、set 或其他）

    Returns:
        JSON 可序列化的对象
    """
    if isinstance(obj, set):
        return sorted(obj)  # 排序保证一致性
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    return obj


__all__ = [
    "convert_lists_to_sets",
    "convert_sets_to_lists",
]