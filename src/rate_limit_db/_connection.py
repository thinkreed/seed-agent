"""数据库连接管理

SQLite 连接创建、初始化、关闭
"""

import asyncio
import contextlib
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger("seed_agent")

T = TypeVar("T")


class DatabaseConnection:
    """数据库连接管理器"""

    def __init__(self, db_path: Path):
        """初始化连接管理器

        Args:
            db_path: 数据库文件路径
        """
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = asyncio.Lock()
        self._close_lock = threading.Lock()

    def get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            try:
                self._local.conn = sqlite3.connect(
                    str(self._db_path), check_same_thread=False, timeout=10.0
                )
                # 启用 WAL 模式
                self._local.conn.execute("PRAGMA journal_mode=WAL")
                self._local.conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.Error:
                logger.exception("Failed to connect to database")
                raise
        return self._local.conn

    def _get_conn(self) -> sqlite3.Connection:
        """向后兼容别名"""
        return self.get_connection()

    async def retry_operation(
        self, operation: Callable[[], T], max_retries: int = 3
    ) -> T:
        """执行数据库操作，带异步重试逻辑

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
                    # 重连
                    with self._close_lock:
                        if (
                            hasattr(self._local, "conn")
                            and self._local.conn is not None
                        ):
                            with contextlib.suppress(sqlite3.Error):
                                self._local.conn.close()
                            self._local.conn = None
                    await asyncio.sleep(0.1 * (attempt + 1))

        logger.error(f"DB operation failed after {max_retries} retries")
        if last_error:
            raise last_error
        raise sqlite3.Error("Unknown database error")

    def init_tables(self) -> None:
        """初始化数据库表"""
        conn = self.get_connection()

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

        # 请求历史表
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

    def close(self) -> None:
        """关闭连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    async def aclose(self) -> None:
        """异步关闭"""
        async with self._lock:
            self.close()

    def get_lock(self) -> asyncio.Lock:
        """获取异步锁"""
        return self._lock