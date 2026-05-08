"""
失效策略 QueryInvalidator

基于 Multica invalidateQueries 设计：
- 实体变更后失效相关缓存，自动重新获取
- 避免 WebSocket 事件直接写入缓存，保证一致性
"""

import fnmatch
import logging
import time
from collections import defaultdict
from typing import Any, Callable

from ._query_invalidator_types import CacheEntry, InvalidationEvent

logger = logging.getLogger("seed_agent")


class QueryInvalidator:
    """查询失效管理器。"""

    def __init__(self) -> None:
        self._entity_keys: dict[str, list[str]] = defaultdict(list)
        self._cache: dict[str, CacheEntry] = {}
        self._invalidation_handlers: list[Callable[[InvalidationEvent], None]] = []
        self._invalidation_history: list[InvalidationEvent] = []

    def register(self, entity: str, query_keys: list[str]) -> None:
        """注册实体与查询键的关联。"""
        for key in query_keys:
            if key not in self._entity_keys[entity]:
                self._entity_keys[entity].append(key)
        logger.debug(f"Registered entity '{entity}' with keys: {query_keys}")

    def unregister(self, entity: str) -> None:
        """取消实体注册"""
        self._entity_keys.pop(entity, None)

    def invalidate(self, entity: str) -> InvalidationEvent:
        """失效实体相关的所有缓存。"""
        affected_keys: list[str] = []
        patterns = self._entity_keys.get(entity, [])

        for key, entry in self._cache.items():
            for pattern in patterns:
                if fnmatch.fnmatch(key, pattern):
                    entry.is_valid = False
                    affected_keys.append(key)
                    break

        event = InvalidationEvent(entity=entity, timestamp=time.time(), affected_keys=affected_keys)
        self._invalidation_history.append(event)

        for handler in self._invalidation_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Invalidation handler error: {e}")

        logger.info(f"Invalidated entity '{entity}', affected {len(affected_keys)} keys")
        return event

    def invalidate_key(self, key: str) -> bool:
        """失效特定键。"""
        entry = self._cache.get(key)
        if entry is None:
            return False
        entry.is_valid = False
        logger.debug(f"Invalidated key '{key}'")
        return True

    def get_cache(self, key: str) -> Any | None:
        """获取缓存数据（失效或不存在返回 None）。"""
        entry = self._cache.get(key)
        if entry is None or not entry.is_valid:
            if entry is not None:
                self._cache.pop(key, None)
            return None
        return entry.data

    def set_cache(self, key: str, data: Any) -> None:
        """设置缓存数据。"""
        self._cache[key] = CacheEntry(key=key, data=data, timestamp=time.time(), is_valid=True)
        logger.debug(f"Set cache for key '{key}'")

    def is_valid(self, key: str) -> bool:
        """检查缓存键是否有效"""
        entry = self._cache.get(key)
        return entry is not None and entry.is_valid

    def clear_all(self) -> None:
        """清除所有缓存"""
        self._cache.clear()
        logger.info("Cleared all cache")

    def subscribe_invalidation(self, handler: Callable[[InvalidationEvent], None]) -> None:
        """订阅失效事件。"""
        self._invalidation_handlers.append(handler)

    def unsubscribe_invalidation(self, handler: Callable[[InvalidationEvent], None]) -> None:
        """取消订阅失效事件"""
        if handler in self._invalidation_handlers:
            self._invalidation_handlers.remove(handler)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        valid_count = sum(1 for e in self._cache.values() if e.is_valid)
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_count,
            "invalid_entries": len(self._cache) - valid_count,
            "registered_entities": list(self._entity_keys.keys()),
            "invalidation_history_count": len(self._invalidation_history),
        }

    def get_last_invalidation(self, entity: str | None = None) -> InvalidationEvent | None:
        """获取最后一次失效事件"""
        if not self._invalidation_history:
            return None
        if entity is None:
            return self._invalidation_history[-1]
        for event in reversed(self._invalidation_history):
            if event.entity == entity:
                return event
        return None

    def __len__(self) -> int:
        return len(self._cache)


# 从子模块重新导出以保持 API 兼容
from ._query_invalidator_globals import get_query_invalidator, setup_default_entities

__all__ = [
    "QueryInvalidator",
    "CacheEntry",
    "InvalidationEvent",
    "get_query_invalidator",
    "setup_default_entities",
]