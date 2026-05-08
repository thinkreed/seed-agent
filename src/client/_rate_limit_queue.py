"""
限流排队模块

阶段1: 排队入场，等待轮次
"""

import logging
from collections.abc import Callable
from typing import Any

from src.request_queue import RequestPriority, TurnTicket, TurnWaitTimeoutError

logger = logging.getLogger("seed_agent")


async def wait_for_turn_and_acquire(
    request_queue: Any,
    queue_started: bool,
    start_queue_dispatcher: Callable[[], Any],
    get_dynamic_timeout: Callable[[RequestPriority], float],
    request_turn: Callable[[RequestPriority], Any],
    priority: RequestPriority,
) -> TurnTicket:
    """阶段 1: 排队入场，等待轮次

    Args:
        request_queue: 请求队列实例
        queue_started: 队列是否已启动
        start_queue_dispatcher: 启动队列调度器的函数
        get_dynamic_timeout: 获取动态超时的函数
        request_turn: 申请轮次的函数
        priority: 请求优先级

    Returns:
        TurnTicket: 轮次票

    Raises:
        ValueError: 队列未初始化
        TurnWaitTimeoutError: 轮次等待超时
    """
    if not request_queue:
        raise ValueError("Request queue not initialized")

    # 确保调度器已启动
    if not queue_started:
        await start_queue_dispatcher()

    # 获取动态超时
    turn_timeout = get_dynamic_timeout(priority)

    # 阶段1：排队入场
    ticket = await request_turn(priority)
    logger.debug(f"Ticket {ticket.id}: submitted (priority={priority.name})")

    try:
        await ticket.wait_for_turn(timeout=turn_timeout)
    except TurnWaitTimeoutError:
        logger.warning(
            f"Ticket {ticket.id}: turn wait timeout ({turn_timeout:.1f}s)"
        )
        raise

    logger.debug(
        f"Ticket {ticket.id}: turn assigned (wait={ticket.get_wait_duration():.2f}s)"
    )
    return ticket