"""LLM 请求限流状态持久化模块入口

重构版本：将大文件拆分为多个小模块
此文件保留为向后兼容的导入入口

模块结构:
- _state.py: RateLimitState 数据类 (~15 行)
- _path.py: 数据库路径获取 (~20 行)
- _connection.py: 连接管理 (~100 行)
- _operations.py: 状态操作 (~100 行)
- _history.py: 历史操作 (~70 行)

总计: 5 个模块，每个均 < 150 行
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
    """SQLite 持久化存储

    特性:
    - 跨进程共享状态
    - WAL 模式高并发
    - 自动清理过期数据
    - 崩溃恢复支持
    """

    def __init__(self, db_path: Path | None = None):
        """
        Args:
            db_path: 数据库路径，默认从 PathsConfig 获取
        """
        self._db_path = db_path or get_db_path()
        self._db_conn = DatabaseConnection(self._db_path)
        self._db_conn.init_tables()

    async def load_state(self) -> RateLimitState:
        """加载当前状态"""
        return await load_state(self._db_conn)

    async def save_state(self, state: RateLimitState) -> None:
        """保存状态"""
        await save_state(self._db_conn, state)

    async def save_bucket_state(self, bucket_state: Any) -> None:
        """保存 Token Bucket 状态"""
        await save_bucket_state(self._db_conn, bucket_state)

    async def save_window_state(self, window_state: Any) -> None:
        """保存滚动窗口状态"""
        await save_window_state(self._db_conn, window_state)

    async def record_request(
        self,
        request_id: str,
        priority: str,
        duration: float | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """记录请求历史"""
        await record_request(
            self._db_conn, request_id, priority, duration, success, error_message
        )

    async def cleanup_old_history(self, max_age: float = 86400.0) -> int:
        """清理过期历史记录"""
        return await cleanup_old_history(self._db_conn, max_age)

    async def get_recent_requests(self, limit: int = 100) -> list[dict]:
        """获取最近的请求历史"""
        return await get_recent_requests(self._db_conn, limit)

    async def get_stats(self) -> dict:
        """获取统计信息"""
        return await get_stats(self._db_conn)

    def close(self) -> None:
        """关闭连接"""
        self._db_conn.close()

    def __del__(self) -> None:
        """析构时确保连接关闭"""
        try:
            self.close()
        except Exception as e:
            logger.debug(f"Exception during __del__ cleanup: {e}")

    async def aclose(self) -> None:
        """异步关闭"""
        await self._db_conn.aclose()


__all__ = ["RateLimitSQLite", "RateLimitState", "get_db_path"]