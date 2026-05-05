"""
限流集成模块

提供:
- RateLimitTimeoutError: 自定义限流超时异常
- init_rate_limiting: 初始化限流组件
- load_queue_config: 加载队列配置
- wait_for_turn_and_acquire: 阶段1-2-3排队等待
- execute_with_concurrency_and_rate_limit: 阶段2-4并发执行
- stream_with_concurrency_and_rate_limit: 阶段2-4流式执行
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from src.rate_limiter import RateLimiter
from src.request_queue import (
    QueueConfig,
    RequestPriority,
    RequestQueue,
    TurnTicket,
    TurnWaitTimeoutError,
)

logger = logging.getLogger("seed_agent")


# 使用自定义限流异常，避免 OpenAI SDK 的类型限制
class RateLimitTimeoutError(Exception):
    """自定义限流等待超时异常"""

    def __init__(self, message: str = "Rate limit wait timeout") -> None:
        super().__init__(message)


def load_queue_config(config: Any) -> QueueConfig:
    """从配置加载 QueueConfig

    Args:
        config: FullConfig 实例

    Returns:
        QueueConfig 实例
    """
    # 尝试从 FullConfig 的 queue 字段加载
    if hasattr(config, "queue") and config.queue:
        return QueueConfig(
            critical_max_size=config.queue.critical_max_size,
            critical_backpressure_threshold=config.queue.critical_backpressure_threshold,
            critical_dispatch_rate=config.queue.critical_dispatch_rate,
            critical_target_wait_time=config.queue.critical_target_wait_time,
            normal_max_size=config.queue.normal_max_size,
            normal_backpressure_threshold=config.queue.normal_backpressure_threshold,
            normal_dispatch_rate=config.queue.normal_dispatch_rate,
            normal_target_wait_time=config.queue.normal_target_wait_time,
            auto_adjust_enabled=config.queue.auto_adjust_enabled,
        )

    # 使用默认值
    return QueueConfig()


async def wait_for_turn_and_acquire(
    request_queue: RequestQueue | None,
    queue_started: bool,
    start_queue_dispatcher: Callable[[], Any],
    get_dynamic_timeout: Callable[[RequestPriority], float],
    request_turn: Callable[[RequestPriority], Any],  # async callable 返回 TurnTicket
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
            # 阶段3：限流检查（CRITICAL 不等待）
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

            # 阶段4：执行
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
