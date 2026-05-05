"""LLM 请求限流状态持久化模块入口

重构版本：将大文件拆分为多个小模块

模块结构:
- _state.py: RateLimitState 数据类 (~16 行)
- _path.py: 数据库路径 (~14 行)
- _connection.py: 连接管理 (~149 行)
- _load_save.py: 状态加载/保存 (~70 行)
- _component_state.py: TokenBucket/Window 状态 (~90 行)
- _history.py: 历史操作 (~126 行)
"""

import logging
from pathlib import Path
from typing import Any

from ._connection import DatabaseConnection
from ._history import cleanup_old_history, get_recent_requests, get_stats
from ._operations import (
    load_state,
    record_request,
    save_bucket_state,
    save_state,
    save_window_state,
)
from ._path import get_db_path
from ._state import RateLimitState

logger = logging.getLogger("seed_agent")


class RateLimitSQLite:
    """SQLite 持久化存储"""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or get_db_path()
        self._db_conn = DatabaseConnection(self._db_path)
        self._db_conn.init_tables()

    async def load_state(self) -> RateLimitState:
        return await load_state(self._db_conn)

    async def save_state(self, state: RateLimitState) -> None:
        await save_state(self._db_conn, state)

    async def save_bucket_state(self, bucket_state: Any) -> None:
        await save_bucket_state(self._db_conn, bucket_state)

    async def save_window_state(self, window_state: Any) -> None:
        await save_window_state(self._db_conn, window_state)

    async def record_request(
        self, request_id: str, priority: str,
        duration: float | None = None, success: bool = True,
        error_message: str | None = None,
    ) -> None:
        await record_request(self._db_conn, request_id, priority, duration, success, error_message)

    async def cleanup_old_history(self, max_age: float = 86400.0) -> int:
        return await cleanup_old_history(self._db_conn, max_age)

    async def get_recent_requests(self, limit: int = 100) -> list[dict]:
        return await get_recent_requests(self._db_conn, limit)

    async def get_stats(self) -> dict:
        return await get_stats(self._db_conn)

    def close(self) -> None:
        self._db_conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as e:
            logger.debug(f"Exception during __del__ cleanup: {e}")

    async def aclose(self) -> None:
        await self._db_conn.aclose()


__all__ = ["RateLimitSQLite", "RateLimitState", "get_db_path"]