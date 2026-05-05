"""
状态持久化模块

提供:
- restore_state: 从持久化恢复限流状态
- save_state: 持久化限流状态
- start_persistence_loop: 启动状态持久化循环
- stop_persistence_loop: 停止状态持久化循环
- persistence_loop: 持久化循环内部实现
- get_persistence_stats: 获取持久化统计信息
"""

import asyncio
import contextlib
import logging
from typing import Any

from src.rate_limit_db import RateLimitSQLite
from src.rate_limiter import RateLimiter, RollingWindowState, TokenBucketState

logger = logging.getLogger("seed_agent")


async def restore_state(
    state_db: RateLimitSQLite | None,
    rate_limiter: RateLimiter | None,
) -> None:
    """从持久化恢复限流状态

    Args:
        state_db: 限流状态数据库实例
        rate_limiter: 限流器实例
    """
    if not state_db or not rate_limiter:
        return

    try:
        state = await state_db.load_state()

        # 恢复 Token Bucket 状态
        bucket_state = TokenBucketState(
            tokens=state.tokens_available, last_refill_time=state.last_refill_time
        )
        rate_limiter.token_bucket.restore_state(bucket_state)

        # 恢复滚动窗口状态
        window_state = RollingWindowState(
            requests=state.requests_in_window,
            total_requests_lifetime=state.total_requests_lifetime,
        )
        rate_limiter.window_tracker.restore_state(window_state)

        logger.info(
            f"Rate limit state restored: "
            f"tokens={state.tokens_available:.1f}, "
            f"window_requests={len(state.requests_in_window)}, "
            f"lifetime_requests={state.total_requests_lifetime}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to restore rate limit state: {type(e).__name__}: {e}"
        )


async def save_state(
    state_db: RateLimitSQLite | None,
    rate_limiter: RateLimiter | None,
) -> None:
    """持久化限流状态

    Args:
        state_db: 限流状态数据库实例
        rate_limiter: 限流器实例
    """
    if not state_db or not rate_limiter:
        return

    try:
        bucket_state, window_state = rate_limiter.get_state()

        # 保存 Token Bucket 状态
        await state_db.save_bucket_state(bucket_state)

        # 保存滚动窗口状态
        await state_db.save_window_state(window_state)

        logger.debug("Rate limit state saved")
    except Exception as e:
        logger.warning(f"Failed to save rate limit state: {type(e).__name__}: {e}")


async def persistence_loop(
    state_db: RateLimitSQLite | None,
    rate_limiter: RateLimiter | None,
    persistence_interval: float,
) -> None:
    """持久化循环内部实现

    Args:
        state_db: 限流状态数据库实例
        rate_limiter: 限流器实例
        persistence_interval: 持久化间隔（秒）
    """
    while True:
        try:
            await asyncio.sleep(persistence_interval)
            await save_state(state_db, rate_limiter)

            # 定期清理过期历史
            if state_db:
                await state_db.cleanup_old_history(max_age=86400.0)

        except asyncio.CancelledError:
            logger.info("Persistence loop cancelled")
            break
        except OSError:
            # 文件系统错误（磁盘满、权限问题等）
            logger.exception("Persistence I/O error")
            await asyncio.sleep(10.0)  # 更长等待避免频繁失败
        except Exception as e:
            logger.exception(f"Persistence loop unexpected error: {e}")
            await asyncio.sleep(5.0)


async def start_persistence_loop(
    state_db: RateLimitSQLite | None,
    rate_limiter: RateLimiter | None,
    persistence_interval: float,
    existing_task: asyncio.Task | None,
) -> asyncio.Task | None:
    """启动状态持久化循环

    Args:
        state_db: 限流状态数据库实例
        rate_limiter: 限流器实例
        persistence_interval: 持久化间隔（秒）
        existing_task: 已存在的持久化任务（如果有）

    Returns:
        持久化任务实例
    """
    if existing_task:
        logger.warning("Persistence loop already running")
        return existing_task

    # 先恢复状态
    await restore_state(state_db, rate_limiter)

    # 启动定时持久化任务
    task = asyncio.create_task(
        persistence_loop(state_db, rate_limiter, persistence_interval)
    )
    logger.info(
        f"State persistence loop started (interval: {persistence_interval}s)"
    )
    return task


async def stop_persistence_loop(
    persistence_task: asyncio.Task | None,
    state_db: RateLimitSQLite | None,
    rate_limiter: RateLimiter | None,
) -> None:
    """停止状态持久化循环

    Args:
        persistence_task: 持久化任务实例
        state_db: 限流状态数据库实例
        rate_limiter: 限流器实例
    """
    if persistence_task:
        persistence_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await persistence_task

        # 最后保存一次状态
        await save_state(state_db, rate_limiter)
        logger.info("State persistence loop stopped")


async def get_persistence_stats(
    state_db: RateLimitSQLite | None,
) -> dict[str, Any] | None:
    """获取持久化统计信息

    Args:
        state_db: 限流状态数据库实例

    Returns:
        统计信息字典，如果 state_db 为 None 则返回 None
    """
    if state_db:
        return await state_db.get_stats()
    return None
