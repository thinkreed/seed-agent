"""限流状态操作

加载、保存限流状态
"""

import json
import logging
import time
from typing import Any

from src.rate_limiter import RollingWindowState, TokenBucketState

from ._connection import DatabaseConnection
from ._state import RateLimitState

logger = logging.getLogger("seed_agent")


async def load_state(db_conn: DatabaseConnection) -> RateLimitState:
    """加载当前状态

    Args:
        db_conn: 数据库连接管理器

    Returns:
        RateLimitState 实例
    """
    async with db_conn.get_lock():
        conn = db_conn.get_connection()
        cursor = conn.execute("""
            SELECT window_requests, tokens_available, last_refill_time,
                   total_requests, updated_at
            FROM rate_limit_state WHERE id = 1
        """)
        row = cursor.fetchone()

        if row:
            window_requests = json.loads(row[0])
            # 清理过期请求（超过 5 小时）
            now = time.time()
            window_requests = [
                t
                for t in window_requests
                if now - t < 18000  # 5 小时
            ]

            return RateLimitState(
                timestamp=row[4],
                tokens_available=row[1],
                last_refill_time=row[2],
                requests_in_window=window_requests,
                total_requests_lifetime=row[3],
            )

        return RateLimitState(timestamp=time.time())


async def save_state(db_conn: DatabaseConnection, state: RateLimitState) -> None:
    """保存状态（带重试）

    Args:
        db_conn: 数据库连接管理器
        state: RateLimitState 实例
    """
    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    window_requests = ?,
                    tokens_available = ?,
                    last_refill_time = ?,
                    total_requests = ?,
                    updated_at = ?
                WHERE id = 1
            """,
                (
                    json.dumps(state.requests_in_window),
                    state.tokens_available,
                    state.last_refill_time,
                    state.total_requests_lifetime,
                    time.time(),
                ),
            )
            conn.commit()

        await db_conn.retry_operation(_save)


async def save_bucket_state(
    db_conn: DatabaseConnection, bucket_state: TokenBucketState
) -> None:
    """保存 Token Bucket 状态

    Args:
        db_conn: 数据库连接管理器
        bucket_state: TokenBucketState 实例
    """
    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    tokens_available = ?,
                    last_refill_time = ?,
                    updated_at = ?
                WHERE id = 1
            """,
                (bucket_state.tokens, bucket_state.last_refill_time, time.time()),
            )
            conn.commit()

        await db_conn.retry_operation(_save)


async def save_window_state(
    db_conn: DatabaseConnection, window_state: RollingWindowState
) -> None:
    """保存滚动窗口状态

    Args:
        db_conn: 数据库连接管理器
        window_state: RollingWindowState 实例
    """
    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    window_requests = ?,
                    total_requests = ?,
                    updated_at = ?
                WHERE id = 1
            """,
                (
                    json.dumps(window_state.requests),
                    window_state.total_requests_lifetime,
                    time.time(),
                ),
            )
            conn.commit()

        await db_conn.retry_operation(_save)


async def record_request(
    db_conn: DatabaseConnection,
    request_id: str,
    priority: str,
    duration: float | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """记录请求历史

    Args:
        db_conn: 数据库连接管理器
        request_id: 请求 ID
        priority: 优先级
        duration: 持续时间
        success: 是否成功
        error_message: 错误信息
    """
    async with db_conn.get_lock():
        conn = db_conn.get_connection()
        conn.execute(
            """
            INSERT INTO request_history (
                request_id, timestamp, priority, duration, success, error_message
            ) VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                request_id,
                time.time(),
                priority,
                duration,
                1 if success else 0,
                error_message,
            ),
        )
        conn.commit()