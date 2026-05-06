"""用户建模数据库初始化

职责:
- 单例模式实现
- 数据库连接管理
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_db_path() -> Path:
    """获取数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir / "user_modeling.db"
    except RuntimeError:
        return Path.home() / ".seed" / "memory" / "user_modeling.db"


USER_MODELING_DB_PATH: Path | None = None


def _ensure_db_path() -> Path:
    """确保数据库路径已初始化"""
    global USER_MODELING_DB_PATH
    if USER_MODELING_DB_PATH is None:
        USER_MODELING_DB_PATH = _get_db_path()
    return USER_MODELING_DB_PATH


class DBConnectionManager:
    """数据库连接管理器"""

    _instance: "DBConnectionManager | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> "DBConnectionManager":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | Path | None = None):
        with DBConnectionManager._lock:
            if DBConnectionManager._initialized:
                return
            DBConnectionManager._initialized = True

        self.db_path = str(db_path or _ensure_db_path())
        self.conn: sqlite3.Connection | None = None
        self._init_connection()

    def _init_connection(self) -> None:
        """初始化连接"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")

    def close(self) -> None:
        """关闭连接"""
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.Error as e:
                logger.warning(f"Database close error: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                DBConnectionManager._instance = None
                DBConnectionManager._initialized = False

    def ensure_conn(self) -> sqlite3.Connection:
        """确保连接可用"""
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn


def get_connection_manager(db_path: str | Path | None = None) -> DBConnectionManager:
    """获取连接管理器单例"""
    return DBConnectionManager(db_path)


__all__ = ["DBConnectionManager", "get_connection_manager", "_ensure_db_path"]