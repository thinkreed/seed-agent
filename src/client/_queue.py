"""
队列管理模块

提供:
- start_queue_dispatcher: 启动队列调度器
- stop_queue_dispatcher: 停止队列调度器
- get_queue_status: 获取队列状态
- request_turn: 申请轮次
"""

import logging
from collections.abc import Callable
from typing import Any

from src.request_queue import RequestPriority, RequestQueue, TurnTicket

logger = logging.getLogger("seed_agent")


async def start_queue_dispatcher(
    request_queue: RequestQueue | None,
    queue_started: bool,
) -> bool:
    """启动队列调度器

    Args:
        request_queue: 请求队列实例
        queue_started: 队列是否已启动

    Returns:
        是否成功启动
    """
    if queue_started:
        return False
    if request_queue:
        await request_queue.start_dispatcher()
        return True
    return False


async def stop_queue_dispatcher(
    request_queue: RequestQueue | None,
    queue_started: bool,
) -> bool:
    """停止队列调度器

    Args:
        request_queue: 请求队列实例
        queue_started: 队列是否已启动

    Returns:
        是否成功停止
    """
    if request_queue and queue_started:
        await request_queue.stop_dispatcher()
        return True
    return False


def get_queue_status(request_queue: RequestQueue | None) -> dict[str, Any] | None:
    """获取队列状态

    Args:
        request_queue: 请求队列实例

    Returns:
        队列状态字典或 None
    """
    if request_queue:
        return request_queue.get_stats()
    return None


async def request_turn(
    request_queue: RequestQueue | None,
    queue_started: bool,
    start_queue_dispatcher_func: Callable[[], Any],
    priority: RequestPriority = RequestPriority.NORMAL,
) -> TurnTicket:
    """申请轮次

    Args:
        request_queue: 请求队列实例
        queue_started: 队列是否已启动
        start_queue_dispatcher_func: 启动队列调度器的函数
        priority: 请求优先级

    Returns:
        TurnTicket 实例

    Raises:
        ValueError: 队列未初始化
    """
    if not request_queue:
        raise ValueError("Request queue not initialized")
    if not queue_started:
        await start_queue_dispatcher_func()
    return await request_queue.request_turn(priority)
