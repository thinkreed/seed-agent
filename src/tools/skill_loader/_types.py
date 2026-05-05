"""
Skill 类型定义模块

包含 Skill 元数据的类型定义，使用 TypedDict 实现类型安全。
"""

from typing import TypedDict


class SkillMetadata(TypedDict, total=False):
    """Skill 元数据类型

    包含: path, dir, name, description, category, version, triggers, platforms 等

    使用 TypedDict 而非 dict 子类，提供类型提示和 IDE 支持。
    """

    path: str
    dir: str
    name: str
    description: str
    category: str
    version: str
    triggers: list[str]
    triggers_lower: set[str]
    platforms: list[str]
    allowed_tools: str
    requires_tools: list[str]
    fallback_for_tools: list[str]
    desc_words: set[str]


# 兼容旧代码的别名
class SkillMeta(dict):
    """Skill 元数据类型 (兼容性别名)

    包含: path, dir, name, description, category, version, triggers, platforms 等

    Deprecated: 请使用 SkillMetadata TypedDict
    """

    pass


__all__ = [
    "SkillMetadata",
    "SkillMeta",
]