"""LLM 请求限流状态持久化

使用 SQLite + WAL 模式实现跨进程共享的限流状态存储
"""

import asyncio
import contextlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from src.rate_limiter import RollingWindowState, TokenBucketState

logger = logging.getLogger("seed_agent")

T = TypeVar("T")


@dataclass
class RateLimitState:
    """完整的限流状态"""

    timestamp: float
    tokens_available: float = 100.0
    last_refill_time: float = 0.0
    requests_in_window: list[float] = field(default_factory=list)
    total_requests_lifetime: int = 0


class RateLimitSQLite:
    """SQLite 持久化存储

    特性:
    - 跨进程共享状态
    - WAL 模式高并发
    - 自动清理过期数据
    - 崩溃恢复支持
    """

    DB_PATH = Path.home() / ".seed" / "rate_limit.db"

    def __init__(self, db_path: Path | None = None):
        """
        Args:
            db_path: 数据库路径，默认 ~/.seed/rate_limit.db
        """
        self._db_path = db_path or self.DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = asyncio.Lock()
        self._close_lock = threading.Lock()  # 线程安全锁保护连接关闭
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            try:
                self._local.conn = sqlite3.connect(
                    str(self._db_path), check_same_thread=False, timeout=10.0
                )
                # 启用 WAL 模式
                self._local.conn.execute("PRAGMA journal_mode=WAL")
                self._local.conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.Error as e:
                logger.error(f"Failed to connect to database: {type(e).__name__}: {e}")
                raise
        return self._local.conn

    async def _retry_db_operation_async(
        self, operation: Callable[[], T], max_retries: int = 3
    ) -> T:
        """
        执行数据库操作，带异步重试逻辑

        Args:
            operation: 数据库操作函数
            max_retries: 最大重试次数

        Returns:
            操作结果

        Raises:
            sqlite3.Error: 重试耗尽后抛出最后一次异常
        """
        last_error: sqlite3.Error | None = None

        for attempt in range(max_retries):
            try:
                return operation()
            except sqlite3.Error as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"DB operation failed (attempt {attempt + 1}/{max_retries}): "
                        f"{type(e).__name__}: {e}. Retrying..."
                    )
                    # 重连：使用类属性锁保护连接关闭，防止竞态条件
                    with self._close_lock:
                        if (
                            hasattr(self._local, "conn")
                            and self._local.conn is not None
                        ):
                            with contextlib.suppress(sqlite3.Error):
                                self._local.conn.close()
                            self._local.conn = None
                    await asyncio.sleep(0.1 * (attempt + 1))  # 异步等待，不阻塞事件循环

        logger.error(f"DB operation failed after {max_retries} retries")
        if last_error:
            # 直接抛出原始异常，避免自引用异常链
            raise last_error
        raise sqlite3.Error("Unknown database error")

    def _init_db(self):
        """初始化数据库"""
        conn = self._get_conn()

        # 限流状态表（单行）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                window_requests TEXT NOT NULL DEFAULT '[]',
                tokens_available REAL NOT NULL DEFAULT 100.0,
                last_refill_time REAL NOT NULL,
                total_requests INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
        """)

        # 初始化默认行
        conn.execute(
            """
            INSERT OR IGNORE INTO rate_limit_state (
                id, window_requests, tokens_available, 
                last_refill_time, total_requests, updated_at
            ) VALUES (1, '[]', 100.0, ?, 0, ?)
        """,
            (time.time(), time.time()),
        )

        # 请求历史表（用于审计）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                priority TEXT NOT NULL,
                duration REAL,
                success INTEGER NOT NULL,
                error_message TEXT
            )
        """)

        # 创建索引
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_request_history_timestamp 
            ON request_history(timestamp)
        """)

        conn.commit()
        logger.info(f"Rate limit database initialized: {self._db_path}")

    async def load_state(self) -> RateLimitState:
        """加载当前状态"""
        async with self._lock:
            conn = self._get_conn()
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

    async def save_state(self, state: RateLimitState) -> None:
        """保存状态（带重试）"""
        async with self._lock:

            def _save():
                conn = self._get_conn()
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

            await self._retry_db_operation_async(_save)

    async def save_bucket_state(self, bucket_state: TokenBucketState) -> None:
        """保存 Token Bucket 状态（带重试）"""
        async with self._lock:

            def _save():
                conn = self._get_conn()
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

            await self._retry_db_operation_async(_save)

    async def save_window_state(self, window_state: RollingWindowState) -> None:
        """保存滚动窗口状态（带重试）"""
        async with self._lock:

            def _save():
                conn = self._get_conn()
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

            await self._retry_db_operation_async(_save)

    async def record_request(
        self,
        request_id: str,
        priority: str,
        duration: float | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """记录请求历史"""
        async with self._lock:
            conn = self._get_conn()
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

    async def cleanup_old_history(self, max_age: float = 86400.0) -> int:
        """清理过期历史记录

        Args:
            max_age: 最大保留时间（秒），默认 24 小时

        Returns:
            清理的记录数
        """
        async with self._lock:
            conn = self._get_conn()
            cutoff = time.time() - max_age
            cursor = conn.execute(
                """
                DELETE FROM request_history WHERE timestamp < ?
            """,
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    async def get_recent_requests(self, limit: int = 100) -> list[dict]:
        """获取最近的请求历史"""
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                """
                SELECT request_id, timestamp, priority, duration, success, error_message
                FROM request_history
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

            return [
                {
                    "request_id": row[0],
                    "timestamp": row[1],
                    "priority": row[2],
                    "duration": row[3],
                    "success": bool(row[4]),
                    "error_message": row[5],
                }
                for row in rows
            ]

    async def get_stats(self) -> dict:
        """获取统计信息"""
        async with self._lock:
            conn = self._get_conn()

            # 总请求数
            cursor = conn.execute("SELECT COUNT(*) FROM request_history")
            total_requests = cursor.fetchone()[0]

            # 成功请求数
            cursor = conn.execute(
                "SELECT COUNT(*) FROM request_history WHERE success = 1"
            )
            successful_requests = cursor.fetchone()[0]

            # 平均耗时
            cursor = conn.execute(
                "SELECT AVG(duration) FROM request_history WHERE duration IS NOT NULL"
            )
            avg_duration = cursor.fetchone()[0] or 0.0

            # 最近错误
            cursor = conn.execute("""
                SELECT request_id, timestamp, error_message
                FROM request_history
                WHERE success = 0
                ORDER BY timestamp DESC
                LIMIT 10
            """)
            recent_errors = [
                {"request_id": row[0], "timestamp": row[1], "error": row[2]}
                for row in cursor.fetchall()
            ]

            return {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": total_requests - successful_requests,
                "success_rate": successful_requests / total_requests
                if total_requests > 0
                else 1.0,
                "avg_duration": avg_duration,
                "recent_errors": recent_errors,
            }

    def close(self):
        """关闭连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __del__(self):
        """析构时确保连接关闭"""
        # __del__ 中不应抛出异常，静默关闭
        # S110/SIM105: __del__ 中不应调用 logger 或使用 contextlib.suppress
        # 因为 Python 解释器可能已在关闭过程中
        try:
            self.close()
        except Exception:
            pass  # 静默忽略，避免 Python 解释器关闭时的警告

    async def aclose(self):
        """异步关闭（用于异步上下文）"""
        async with self._lock:
            self.close()
