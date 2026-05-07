"""
DataHub Pub/Sub 实现

基于 FinceptTerminal DataHub 设计：
- Topic 发布订阅模式
- 请求去重（多订阅者同一 topic → 单次获取）
- TopicPolicy 管理（TTL、Rate Limit、Refresh）
- Pattern 匹配支持

使用示例：
    hub = DataHub()

    # 发布数据
    hub.publish("memory:search:query", {"query": "test", "results": [...]})

    # 订阅 Topic
    hub.subscribe("memory:search:*", lambda topic, data: print(topic, data))

    # 设置策略
    hub.set_policy("memory:*", TopicPolicy(ttl_seconds=60))

    # 获取最后数据
    data = hub.get_last("memory:search:query")
"""

import asyncio
import fnmatch
import logging
import time
from collections import defaultdict
from typing import Any

from ._datahub_types import (
    PatternHandler,
    PublishEvent,
    TopicEntry,
    TopicHandler,
    TopicPolicy,
)

logger = logging.getLogger("seed_agent")


class DataHub:
    """
    Topic-based Pub/Sub 数据分发中心。

    功能：
    - publish: 发布数据到 Topic
    - subscribe: 订阅 Topic（精确匹配）
    - subscribe_pattern: 订阅模式（通配符匹配）
    - get_last: 获取最后发布的数据
    - set_policy: 设置 Topic 策略
    """

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
        self._pattern_subscribers: dict[str, list[PatternHandler]] = defaultdict(
            list
        )
        self._policies: dict[str, TopicPolicy] = {}
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}
        self._rate_limits: dict[str, list[float]] = {}
        self._initialized = True

    def publish(
        self,
        topic: str,
        data: Any,
        source: str | None = None,
    ) -> None:
        """
        发布数据到 Topic。

        Args:
            topic: Topic 名称（格式: category:subcategory:id）
            data: 数据内容
            source: 来源标识（可选）
        """
        event = PublishEvent(
            topic=topic,
            data=data,
            timestamp=time.time(),
            source=source,
        )

        # 缓存数据
        policy = self._get_policy(topic)
        if policy.cache_enabled:
            self._topic_cache[topic] = TopicEntry(
                topic=topic,
                data=data,
                timestamp=event.timestamp,
                policy=policy,
            )

        # 通知精确订阅者
        for handler in self._subscribers.get(topic, []):
            try:
                handler(topic, data)
            except Exception as e:
                logger.warning(f"Handler error for {topic}: {e}")

        # 通知模式订阅者
        for pattern, handlers in self._pattern_subscribers.items():
            if self._matches_pattern(pattern, topic):
                for handler in handlers:
                    try:
                        handler(pattern, topic, data)
                    except Exception as e:
                        logger.warning(
                            f"Pattern handler error for {pattern}/{topic}: {e}"
                        )

        # 完成 pending requests
        if topic in self._pending_requests:
            future = self._pending_requests.pop(topic)
            if not future.done():
                future.set_result(data)

        logger.debug(f"Published to {topic}: {type(data).__name__}")

    def subscribe(
        self,
        topic: str,
        handler: TopicHandler,
    ) -> None:
        """
        订阅 Topic（精确匹配）。

        Args:
            topic: Topic 名称
            handler: 处理函数 (topic, data) -> None
        """
        self._subscribers[topic].append(handler)

        # 如果有缓存数据，立即通知
        if topic in self._topic_cache:
            entry = self._topic_cache[topic]
            if not self._is_expired(entry):
                try:
                    handler(topic, entry.data)
                except Exception as e:
                    logger.warning(f"Handler error for cached {topic}: {e}")

    def subscribe_pattern(
        self,
        pattern: str,
        handler: PatternHandler,
    ) -> None:
        """
        订阅模式（通配符匹配）。

        Args:
            pattern: 模式（如 "memory:*", "tool:execute:*"）
            handler: 处理函数 (pattern, topic, data) -> None
        """
        self._pattern_subscribers[pattern].append(handler)

        # 通知已有缓存的匹配 Topic
        for topic, entry in self._topic_cache.items():
            if self._matches_pattern(pattern, topic) and not self._is_expired(entry):
                try:
                    handler(pattern, topic, entry.data)
                except Exception as e:
                    logger.warning(
                        f"Pattern handler error for cached {pattern}/{topic}: {e}"
                    )

    def unsubscribe(self, topic: str, handler: TopicHandler | None = None) -> None:
        """
        取消订阅。

        Args:
            topic: Topic 名称
            handler: 特定处理函数（None = 移除所有）
        """
        if handler is None:
            self._subscribers.pop(topic, None)
        else:
            handlers = self._subscribers.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

    def unsubscribe_pattern(
        self, pattern: str, handler: PatternHandler | None = None
    ) -> None:
        """
        取消模式订阅。

        Args:
            pattern: 模式
            handler: 特定处理函数（None = 移除所有）
        """
        if handler is None:
            self._pattern_subscribers.pop(pattern, None)
        else:
            handlers = self._pattern_subscribers.get(pattern, [])
            if handler in handlers:
                handlers.remove(handler)

    def get_last(self, topic: str) -> Any | None:
        """
        获取 Topic 最后发布的数据。

        Args:
            topic: Topic 名称

        Returns:
            数据内容（过期或不存在返回 None）
        """
        entry = self._topic_cache.get(topic)
        if entry is None:
            return None

        if self._is_expired(entry):
            self._topic_cache.pop(topic, None)
            return None

        return entry.data

    def has_topic(self, topic: str) -> bool:
        """检查 Topic 是否有缓存数据"""
        entry = self._topic_cache.get(topic)
        if entry is None:
            return False
        return not self._is_expired(entry)

    def clear_topic(self, topic: str) -> None:
        """清除 Topic 缓存"""
        self._topic_cache.pop(topic, None)

    def clear_all(self) -> None:
        """清除所有缓存"""
        self._topic_cache.clear()

    def set_policy(self, pattern: str, policy: TopicPolicy) -> None:
        """
        设置 Topic 策略。

        Args:
            pattern: 模式（如 "memory:*"）
            policy: 策略配置
        """
        self._policies[pattern] = policy

    def _get_policy(self, topic: str) -> TopicPolicy:
        """获取 Topic 的策略"""
        for pattern, policy in self._policies.items():
            if self._matches_pattern(pattern, topic):
                return policy
        return TopicPolicy()

    def _matches_pattern(self, pattern: str, topic: str) -> bool:
        """检查 Topic 是否匹配模式"""
        # 使用 fnmatch 进行通配符匹配
        return fnmatch.fnmatch(topic, pattern)

    def _is_expired(self, entry: TopicEntry) -> bool:
        """检查条目是否过期"""
        if entry.policy.ttl_seconds == 0:
            return False  # 无过期时间

        elapsed = time.time() - entry.timestamp
        return elapsed > entry.policy.ttl_seconds

    async def request_topic(
        self,
        topic: str,
        fetch_fn: callable | None = None,
    ) -> Any:
        """
        请求 Topic 数据（带去重）。

        Args:
            topic: Topic 名称
            fetch_fn: 获取数据的函数（None = 仅等待）

        Returns:
            数据内容

        Note:
            多个请求同一 Topic 时，仅执行一次 fetch_fn。
        """
        # 检查缓存
        cached = self.get_last(topic)
        if cached is not None:
            return cached

        policy = self._get_policy(topic)

        # 检查 rate limit
        if policy.rate_limit_per_minute > 0:
            now = time.time()
            requests = self._rate_limits.get(topic, [])
            # 移除 60 秒前的请求
            requests = [t for t in requests if now - t < 60]
            if len(requests) >= policy.rate_limit_per_minute:
                logger.warning(f"Rate limit exceeded for {topic}")
                raise RuntimeError(f"Rate limit exceeded for {topic}")
            requests.append(now)
            self._rate_limits[topic] = requests

        # 检查 pending request（去重）
        if topic in self._pending_requests:
            return await self._pending_requests[topic]

        # 创建新的 Future
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending_requests[topic] = future

        # 执行 fetch
        if fetch_fn is not None:
            try:
                if asyncio.iscoroutinefunction(fetch_fn):
                    data = await fetch_fn()
                else:
                    data = fetch_fn()
                self.publish(topic, data)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)
                self._pending_requests.pop(topic, None)
                raise

        return await future

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "topics_cached": len(self._topic_cache),
            "exact_subscribers": {
                t: len(h) for t, h in self._subscribers.items() if h
            },
            "pattern_subscribers": {
                p: len(h) for p, h in self._pattern_subscribers.items() if h
            },
            "pending_requests": len(self._pending_requests),
            "policies": list(self._policies.keys()),
        }

    def __len__(self) -> int:
        return len(self._topic_cache)


def get_datahub() -> DataHub:
    """获取 DataHub 单例"""
    return DataHub()


__all__ = ["DataHub", "get_datahub"]