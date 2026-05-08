"""
限流执行模块

阶段2-4: 并发控制、限流检查、执行
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from src.rate_limiter import RateLimiter
from src.request_queue import RequestPriority, TurnTicket

from ._rate_limit_types import RateLimitTimeoutError

logger = logging.getLogger("seed_agent")


async def execute_with_concurrency_and_rate_limit(
    semaphore: asyncio.Semaphore | None,
    rate_limiter: RateLimiter | None,
    active_count_lock: asyncio.Lock,
    active_count: int,
    ticket: TurnTicket,
    priority: RequestPriority,
    execution_func: Callable[[], Any],
    is_stream: bool = False,
):
    """阶段 2-4: 获取信号量、限流并执行（非流式）

    Args:
        semaphore: 并发信号量
        rate_limiter: 限流器
        active_count_lock: 活跃计数锁
        active_count: 活跃计数（引用，会被修改）
        ticket: 轮次票
        priority: 请求优先级
        execution_func: 执行函数
        is_stream: 是否为流式请求

    Returns:
        执行结果

    Raises:
        ValueError: Semaphore 未初始化
        RateLimitTimeoutError: 限流等待超时
    """
    if not semaphore:
        raise ValueError("Request semaphore not initialized")

    async with semaphore:
        logger.debug(
            f"Ticket {ticket.id}: concurrent acquired{' (stream)' if is_stream else ''}"
        )

        async with active_count_lock:
            active_count += 1

        try:
            # 阶段三：限流检查（CRITICAL 不等待）
            if rate_limiter:
                max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                acquired = await rate_limiter.wait_and_acquire(max_wait=max_wait)
                if not acquired:
                    raise RateLimitTimeoutError(
                        "Rate limit wait timeout, please retry later"
                    )

            logger.debug(
                f"Ticket {ticket.id}: rate limit acquired{' (stream)' if is_stream else ''}"
            )

            # 阶段四：执行
            return await execution_func()

        finally:
            async with active_count_lock:
                active_count -= 1


async def stream_with_concurrency_and_rate_limit(
    semaphore: asyncio.Semaphore | None,
    rate_limiter: RateLimiter | None,
    active_count_lock: asyncio.Lock,
    active_count: int,
    ticket: TurnTicket,
    priority: RequestPriority,
    stream_func: Callable[[], AsyncGenerator[dict, None]],
) -> AsyncGenerator[dict, None]:
    """阶段 2-4: 获取信号量、限流并执行（流式）

    注意：此方法现在是异步生成器，直接 yield 数据

    Args:
        semaphore: 并发信号量
        rate_limiter: 限流器
        active_count_lock: 活跃计数锁
        active_count: 活跃计数（引用，会被修改）
        ticket: 轮次票
        priority: 请求优先级
        stream_func: 流式生成函数

    Yields:
        流式数据块

    Raises:
        RuntimeError: Semaphore 未初始化
        RateLimitTimeoutError: 限流等待超时
    """
    # 确保 semaphore 已初始化（显式检查避免优化模式问题）
    if semaphore is None:
        raise RuntimeError(
            "Request semaphore not initialized - "
            "check init_rate_limiting() was called during construction"
        )

    async with semaphore:
        logger.debug(f"Ticket {ticket.id}: concurrent acquired (stream)")

        async with active_count_lock:
            active_count += 1

        try:
            if rate_limiter:
                max_wait = 0.0 if priority == RequestPriority.CRITICAL else 60.0
                acquired = await rate_limiter.wait_and_acquire(max_wait=max_wait)
                if not acquired:
                    raise RateLimitTimeoutError(
                        "Rate limit wait timeout, please retry later"
                    )

            logger.debug(f"Ticket {ticket.id}: rate limit acquired (stream)")

            async for chunk in stream_func():
                yield chunk

            logger.debug(f"Ticket {ticket.id}: stream completed")

        finally:
            async with active_count_lock:
                active_count -= 1