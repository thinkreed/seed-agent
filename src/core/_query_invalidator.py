"""
失效策略 QueryInvalidator

基于 Multica invalidateQueries 设计：
- 实体变更后失效相关缓存，自动重新获取
- 避免 WebSocket 事件直接写入缓存，保证一致性
- 实体 → 查询键映射，支持批量失效

使用示例：
    invalidator = QueryInvalidator()

    # 注册实体关联
    invalidator.register("memory", ["memory:search:*", "memory:list"])

    # 失效实体缓存
    invalidator.invalidate("memory")

    # 与 DataHub 集成
    hub.subscribe("memory:updated", lambda t, d: invalidator.invalidate("memory"))
"""

import fnmatch
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("seed_agent")


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


class QueryInvalidator:
    """
    查询失效管理器。

    功能：
    - register: 注册实体与查询键的关联
    - invalidate: 失效实体相关的所有缓存
    - get_cache: 获取缓存数据（自动检查是否失效）
    - set_cache: 设置缓存数据
    - subscribe_invalidation: 订阅失效事件
    """

    def __init__(self) -> None:
        self._entity_keys: dict[str, list[str]] = defaultdict(list)
        self._cache: dict[str, CacheEntry] = {}
        self._invalidation_handlers: list[Callable[[InvalidationEvent], None]] = []
        self._invalidation_history: list[InvalidationEvent] = []

    def register(self, entity: str, query_keys: list[str]) -> None:
        """
        注册实体与查询键的关联。

        Args:
            entity: 实体名称（如 "memory", "session", "tool"）
            query_keys: 相关的查询键模式（支持通配符）
        """
        for key in query_keys:
            if key not in self._entity_keys[entity]:
                self._entity_keys[entity].append(key)
        logger.debug(f"Registered entity '{entity}' with keys: {query_keys}")

    def unregister(self, entity: str) -> None:
        """取消实体注册"""
        self._entity_keys.pop(entity, None)

    def invalidate(self, entity: str) -> InvalidationEvent:
        """
        失效实体相关的所有缓存。

        Args:
            entity: 实体名称

        Returns:
            失效事件（包含受影响的键列表）
        """
        affected_keys: list[str] = []
        patterns = self._entity_keys.get(entity, [])

        # 遍历缓存，匹配模式的标记为失效
        for key, entry in self._cache.items():
            for pattern in patterns:
                if fnmatch.fnmatch(key, pattern):
                    entry.is_valid = False
                    affected_keys.append(key)
                    break

        # 记录失效事件
        event = InvalidationEvent(
            entity=entity,
            timestamp=time.time(),
            affected_keys=affected_keys,
        )
        self._invalidation_history.append(event)

        # 通知订阅者
        for handler in self._invalidation_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Invalidation handler error: {e}")

        logger.info(
            f"Invalidated entity '{entity}', affected {len(affected_keys)} keys"
        )
        return event

    def invalidate_key(self, key: str) -> bool:
        """
        失效特定键。

        Args:
            key: 缓存键

        Returns:
            是否成功失效
        """
        entry = self._cache.get(key)
        if entry is None:
            return False

        entry.is_valid = False
        logger.debug(f"Invalidated key '{key}'")
        return True

    def get_cache(self, key: str) -> Any | None:
        """
        获取缓存数据。

        Args:
            key: 缓存键

        Returns:
            数据内容（失效或不存在返回 None）
        """
        entry = self._cache.get(key)
        if entry is None or not entry.is_valid:
            # 清除失效的条目
            if entry is not None:
                self._cache.pop(key, None)
            return None

        return entry.data

    def set_cache(self, key: str, data: Any) -> None:
        """
        设置缓存数据。

        Args:
            key: 缓存键
            data: 数据内容
        """
        self._cache[key] = CacheEntry(
            key=key,
            data=data,
            timestamp=time.time(),
            is_valid=True,
        )
        logger.debug(f"Set cache for key '{key}'")

    def is_valid(self, key: str) -> bool:
        """检查缓存键是否有效"""
        entry = self._cache.get(key)
        return entry is not None and entry.is_valid

    def clear_all(self) -> None:
        """清除所有缓存"""
        self._cache.clear()
        logger.info("Cleared all cache")

    def subscribe_invalidation(
        self, handler: Callable[[InvalidationEvent], None]
    ) -> None:
        """
        订阅失效事件。

        Args:
            handler: 处理函数 (event) -> None
        """
        self._invalidation_handlers.append(handler)

    def unsubscribe_invalidation(
        self, handler: Callable[[InvalidationEvent], None]
    ) -> None:
        """取消订阅失效事件"""
        if handler in self._invalidation_handlers:
            self._invalidation_handlers.remove(handler)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        valid_count = sum(1 for e in self._cache.values() if e.is_valid)
        invalid_count = len(self._cache) - valid_count

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_count,
            "invalid_entries": invalid_count,
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


# 全局实例
_query_invalidator: QueryInvalidator | None = None


def get_query_invalidator() -> QueryInvalidator:
    """获取全局 QueryInvalidator 实例"""
    if _query_invalidator is None:
        _query_invalidator = QueryInvalidator()
    return _query_invalidator


def setup_default_entities() -> None:
    """设置默认实体关联"""
    invalidator = get_query_invalidator()

    # 记忆相关
    invalidator.register("memory", [
        "memory:search:*",
        "memory:list",
        "memory:detail:*",
    ])

    # 会话相关
    invalidator.register("session", [
        "session:list",
        "session:detail:*",
        "session:events:*",
    ])

    # 工具相关
    invalidator.register("tool", [
        "tool:list",
        "tool:detail:*",
        "tool:execute:*",
    ])

    # LLM 相关
    invalidator.register("llm", [
        "llm:call:*",
        "llm:stream:*",
        "llm:stats",
    ])

    # 自主探索相关
    invalidator.register("autonomous", [
        "autonomous:status",
        "autonomous:history",
    ])


__all__ = [
    "QueryInvalidator",
    "CacheEntry",
    "InvalidationEvent",
    "get_query_invalidator",
    "setup_default_entities",
]