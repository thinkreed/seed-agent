"""TokenBucket 和 RollingWindow 状态保存

保存特定限流组件的状态
"""

import logging
import time

from src.rate_limiter import RollingWindowState, TokenBucketState

from ._connection import DatabaseConnection

logger = logging.getLogger("seed_agent")


async def save_bucket_state(db_conn: DatabaseConnection, bucket_state: TokenBucketState) -> None:
    """保存 Token Bucket 状态"""
    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    tokens_available = ?, last_refill_time = ?, updated_at = ?
                WHERE id = 1
            """,
                (bucket_state.tokens, bucket_state.last_refill_time, time.time()),
            )
            conn.commit()

        await db_conn.retry_operation(_save)


async def save_window_state(db_conn: DatabaseConnection, window_state: RollingWindowState) -> None:
    """保存滚动窗口状态"""
    import json

    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    window_requests = ?, total_requests = ?, updated_at = ?
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
    """记录请求历史"""
    async with db_conn.get_lock():
        conn = db_conn.get_connection()
        conn.execute(
            """
            INSERT INTO request_history (
                request_id, timestamp, priority, duration, success, error_message
            ) VALUES (?, ?, ?, ?, ?, ?)
        """,
            (request_id, time.time(), priority, duration, 1 if success else 0, error_message),
        )
        conn.commit()