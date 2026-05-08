"""
DataHub Pub/Sub 实现

基于 FinceptTerminal DataHub 设计：Topic 发布订阅、请求去重、策略管理、Pattern 匹配。

使用: hub.publish("memory:search:query", data)
     hub.subscribe("memory:search:*", handler)
     hub.set_policy("memory:*", TopicPolicy(ttl_seconds=60))
"""

import asyncio
import fnmatch
import logging
import time
from collections import defaultdict
from typing import Any

from ._datahub_publish import publish as _publish
from ._datahub_publish import request_topic as _request_topic
from ._datahub_subscribe import (
    subscribe as _subscribe,
    subscribe_pattern as _subscribe_pattern,
    unsubscribe as _unsubscribe,
    unsubscribe_pattern as _unsubscribe_pattern,
)
from ._datahub_types import PatternHandler, TopicEntry, TopicHandler, TopicPolicy

logger = logging.getLogger("seed_agent")


class DataHub:
    """Topic-based Pub/Sub 数据分发中心。"""

    _instance: "DataHub | None" = None

    def __new__(cls) -> "DataHub":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._topic_cache: dict[str, TopicEntry] = {}
        self._subscribers: dict[str, list[TopicHandler]] = defaultdict(list)
        self._pattern_subscribers: dict[str, list[PatternHandler]] = defaultdict(list)
        self._policies: dict[str, TopicPolicy] = {}
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}
        self._rate_limits: dict[str, list[float]] = {}
        self._initialized = True

    # === 订阅管理 ===

    def subscribe(self, topic: str, handler: TopicHandler) -> None:
        """订阅 Topic（精确匹配）。"""
        _subscribe(self, topic, handler)

    def subscribe_pattern(self, pattern: str, handler: PatternHandler) -> None:
        """订阅模式（通配符匹配）。"""
        _subscribe_pattern(self, pattern, handler)

    def unsubscribe(self, topic: str, handler: TopicHandler | None = None) -> None:
        """取消订阅。"""
        _unsubscribe(self, topic, handler)

    def unsubscribe_pattern(
        self, pattern: str, handler: PatternHandler | None = None
    ) -> None:
        """取消模式订阅。"""
        _unsubscribe_pattern(self, pattern, handler)

    # === 发布管理 ===

    def publish(self, topic: str, data: Any, source: str | None = None) -> None:
        """发布数据到 Topic。"""
        _publish(self, topic, data, source)

    async def request_topic(self, topic: str, fetch_fn: callable | None = None) -> Any:
        """请求 Topic 数据（带去重）。"""
        return await _request_topic(self, topic, fetch_fn)

    # === 缓存管理 ===

    def get_last(self, topic: str) -> Any | None:
        """获取 Topic 最后发布的数据。"""
        entry = self._topic_cache.get(topic)
        if entry is None:
            return None
        if self._is_expired(entry):
            self._topic_cache.pop(topic, None)
            return None
        return entry.data

    def has_topic(self, topic: str) -> bool:
        """检查 Topic 是否有缓存数据。"""
        entry = self._topic_cache.get(topic)
        return entry is not None and not self._is_expired(entry)

    def clear_topic(self, topic: str) -> None:
        """清除 Topic 缓存。"""
        self._topic_cache.pop(topic, None)

    def clear_all(self) -> None:
        """清除所有缓存。"""
        self._topic_cache.clear()

    # === 策略管理 ===

    def set_policy(self, pattern: str, policy: TopicPolicy) -> None:
        """设置 Topic 策略。"""
        self._policies[pattern] = policy

    def _get_policy(self, topic: str) -> TopicPolicy:
        """获取 Topic 的策略。"""
        for pattern, policy in self._policies.items():
            if self._matches_pattern(pattern, topic):
                return policy
        return TopicPolicy()

    # === 辅助方法 ===

    def _matches_pattern(self, pattern: str, topic: str) -> bool:
        """检查 Topic 是否匹配模式。"""
        return fnmatch.fnmatch(topic, pattern)

    def _is_expired(self, entry: TopicEntry) -> bool:
        """检查条目是否过期。"""
        if entry.policy.ttl_seconds == 0:
            return False
        return time.time() - entry.timestamp > entry.policy.ttl_seconds

    # === 统计 ===

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        return {
            "topics_cached": len(self._topic_cache),
            "exact_subscribers": {t: len(h) for t, h in self._subscribers.items() if h},
            "pattern_subscribers": {
                p: len(h) for p, h in self._pattern_subscribers.items() if h
            },
            "pending_requests": len(self._pending_requests),
            "policies": list(self._policies.keys()),
        }

    def __len__(self) -> int:
        return len(self._topic_cache)


def get_datahub() -> DataHub:
    """获取 DataHub 单例。"""
    return DataHub()


__all__ = ["DataHub", "get_datahub"]