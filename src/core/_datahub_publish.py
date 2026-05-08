"""
DataHub 发布管理模块

包含 publish/request_topic 相关逻辑。
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._datahub import DataHub

from ._datahub_types import PublishEvent, TopicEntry

logger = logging.getLogger("seed_agent")


def publish(
    hub: "DataHub",
    topic: str,
    data: Any,
    source: str | None = None,
) -> None:
    """
    发布数据到 Topic。

    Args:
        hub: DataHub 实例
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
    policy = hub._get_policy(topic)
    if policy.cache_enabled:
        hub._topic_cache[topic] = TopicEntry(
            topic=topic,
            data=data,
            timestamp=event.timestamp,
            policy=policy,
        )

    # 通知精确订阅者
    for handler in hub._subscribers.get(topic, []):
        try:
            handler(topic, data)
        except Exception as e:
            logger.warning(f"Handler error for {topic}: {e}")

    # 通知模式订阅者
    for pattern, handlers in hub._pattern_subscribers.items():
        if hub._matches_pattern(pattern, topic):
            for handler in handlers:
                try:
                    handler(pattern, topic, data)
                except Exception as e:
                    logger.warning(
                        f"Pattern handler error for {pattern}/{topic}: {e}"
                    )

    # 完成 pending requests
    if topic in hub._pending_requests:
        future = hub._pending_requests.pop(topic)
        if not future.done():
            future.set_result(data)

    logger.debug(f"Published to {topic}: {type(data).__name__}")


async def request_topic(
    hub: "DataHub",
    topic: str,
    fetch_fn: callable | None = None,
) -> Any:
    """
    请求 Topic 数据（带去重）。

    Args:
        hub: DataHub 实例
        topic: Topic 名称
        fetch_fn: 获取数据的函数（None = 仅等待）

    Returns:
        数据内容

    Note:
        多个请求同一 Topic 时，仅执行一次 fetch_fn。
    """
    # 检查缓存
    cached = hub.get_last(topic)
    if cached is not None:
        return cached

    policy = hub._get_policy(topic)

    # 检查 rate limit
    if policy.rate_limit_per_minute > 0:
        now = time.time()
        requests = hub._rate_limits.get(topic, [])
        # 移除 60 秒前的请求
        requests = [t for t in requests if now - t < 60]
        if len(requests) >= policy.rate_limit_per_minute:
            logger.warning(f"Rate limit exceeded for {topic}")
            raise RuntimeError(f"Rate limit exceeded for {topic}")
        requests.append(now)
        hub._rate_limits[topic] = requests

    # 检查 pending request（去重）
    if topic in hub._pending_requests:
        return await hub._pending_requests[topic]

    # 创建新的 Future
    future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
    hub._pending_requests[topic] = future

    # 执行 fetch
    if fetch_fn is not None:
        try:
            if asyncio.iscoroutinefunction(fetch_fn):
                data = await fetch_fn()
            else:
                data = fetch_fn()
            publish(hub, topic, data)
        except Exception as e:
            if not future.done():
                future.set_exception(e)
            hub._pending_requests.pop(topic, None)
            raise

    return await future