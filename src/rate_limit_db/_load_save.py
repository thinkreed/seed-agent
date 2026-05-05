"""限流状态加载/保存

加载和保存完整状态
"""

import json
import logging
import time

from ._connection import DatabaseConnection
from ._state import RateLimitState

logger = logging.getLogger("seed_agent")


async def load_state(db_conn: DatabaseConnection) -> RateLimitState:
    """加载当前状态"""
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
            now = time.time()
            window_requests = [t for t in window_requests if now - t < 18000]

            return RateLimitState(
                timestamp=row[4],
                tokens_available=row[1],
                last_refill_time=row[2],
                requests_in_window=window_requests,
                total_requests_lifetime=row[3],
            )

        return RateLimitState(timestamp=time.time())


async def save_state(db_conn: DatabaseConnection, state: RateLimitState) -> None:
    """保存状态"""
    async with db_conn.get_lock():

        def _save():
            conn = db_conn.get_connection()
            conn.execute(
                """
                UPDATE rate_limit_state SET
                    window_requests = ?, tokens_available = ?, last_refill_time = ?,
                    total_requests = ?, updated_at = ?
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