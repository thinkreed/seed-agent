"""
DataHub 订阅管理模块

包含 subscribe/unsubscribe/subscribe_pattern 相关逻辑。
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._datahub import DataHub

from ._datahub_types import PatternHandler, TopicHandler

logger = logging.getLogger("seed_agent")


def subscribe(
    hub: "DataHub",
    topic: str,
    handler: TopicHandler,
) -> None:
    """
    订阅 Topic（精确匹配）。

    Args:
        hub: DataHub 实例
        topic: Topic 名称
        handler: 处理函数 (topic, data) -> None
    """
    hub._subscribers[topic].append(handler)

    # 如果有缓存数据，立即通知
    if topic in hub._topic_cache:
        entry = hub._topic_cache[topic]
        if not hub._is_expired(entry):
            try:
                handler(topic, entry.data)
            except Exception as e:
                logger.warning(f"Handler error for cached {topic}: {e}")


def subscribe_pattern(
    hub: "DataHub",
    pattern: str,
    handler: PatternHandler,
) -> None:
    """
    订阅模式（通配符匹配）。

    Args:
        hub: DataHub 实例
        pattern: 模式（如 "memory:*", "tool:execute:*"）
        handler: 处理函数 (pattern, topic, data) -> None
    """
    hub._pattern_subscribers[pattern].append(handler)

    # 通知已有缓存的匹配 Topic
    for topic, entry in hub._topic_cache.items():
        if hub._matches_pattern(pattern, topic) and not hub._is_expired(entry):
            try:
                handler(pattern, topic, entry.data)
            except Exception as e:
                logger.warning(
                    f"Pattern handler error for cached {pattern}/{topic}: {e}"
                )


def unsubscribe(
    hub: "DataHub",
    topic: str,
    handler: TopicHandler | None = None,
) -> None:
    """
    取消订阅。

    Args:
        hub: DataHub 实例
        topic: Topic 名称
        handler: 特定处理函数（None = 移除所有）
    """
    if handler is None:
        hub._subscribers.pop(topic, None)
    else:
        handlers = hub._subscribers.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)


def unsubscribe_pattern(
    hub: "DataHub",
    pattern: str,
    handler: PatternHandler | None = None,
) -> None:
    """
    取消模式订阅。

    Args:
        hub: DataHub 实例
        pattern: 模式
        handler: 特定处理函数（None = 移除所有）
    """
    if handler is None:
        hub._pattern_subscribers.pop(pattern, None)
    else:
        handlers = hub._pattern_subscribers.get(pattern, [])
        if handler in handlers:
            handlers.remove(handler)