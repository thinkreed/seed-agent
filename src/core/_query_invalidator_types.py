"""
QueryInvalidator 数据类型定义

基于 Multica invalidateQueries 设计的数据类型。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    """缓存条目"""

    key: str
    data: Any
    timestamp: float
    is_valid: bool = True


@dataclass
class InvalidationEvent:
    """失效事件"""

    entity: str
    timestamp: float
    affected_keys: list[str] = field(default_factory=list)


__all__ = [
    "CacheEntry",
    "InvalidationEvent",
]