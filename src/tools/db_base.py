"""
数据库单例基类 - Database Singleton Base

提供线程安全的单例数据库连接管理基类。

核心特性:
- 单例模式：全局唯一实例
- 线程安全：双重检查锁定模式
- 连接管理：自动初始化和关闭
- WAL 模式：性能优化配置

使用:
    class MyDB(SingletonDB):
        def _create_schema(self) -> None:
            # 实现具体的 Schema 创建逻辑
            ...

    db = MyDB(db_path="/path/to/db.sqlite")
    conn = db._ensure_conn()
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Self, cast

logger = logging.getLogger(__name__)


class SingletonDB:
    """单例数据库基类

    使用双重检查锁定模式确保线程安全的单例创建。

    子类需要实现:
    - _create_schema(): 创建具体的数据库 Schema

    子类可以覆盖:
    - _get_default_path(): 返回默认数据库路径
    - _init_db(): 自定义初始化逻辑

    Example: 参见 SessionDB, UserModelingLayer, LongTermArchiveLayer
    """

    _instance: "SingletonDB | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> Self:
        """单例模式：确保全局只有一个实例（线程安全）

        使用双重检查锁定模式，避免不必要的锁开销。
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(self, db_path: str | Path | None = None):
        """初始化数据库连接

        使用类锁保护初始化状态检查，避免重复初始化。
        """
        # 使用类属性名获取锁（子类应该有自己的锁）
        lock_attr = f"{self.__class__.__name__}._lock"
        lock = self.__class__._lock

        with lock:
            if self.__class__._initialized:
                return
            self.__class__._initialized = True

        self.db_path = str(db_path or self._get_default_path())
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_default_path(self) -> Path:
        """获取默认数据库路径（子类应覆盖）

        Returns:
            默认数据库路径
        """
        return Path.home() / ".seed" / "default.db"

    def _init_db(self) -> None:
        """初始化数据库连接和 Schema"""
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # 创建连接（单例模式允许跨线程访问）
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # 性能优化 PRAGMA
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-32000;")

        # 创建 Schema
        self._create_schema()

    def _create_schema(self) -> None:
        """创建数据库 Schema（子类必须实现）"""
        raise NotImplementedError("Subclasses must implement _create_schema()")

    def _ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用

        Returns:
            活动的数据库连接

        Raises:
            RuntimeError: 连接已关闭
        """
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def close(self) -> None:
        """关闭数据库连接，释放资源并重置单例状态"""
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.OperationalError as e:
                logger.warning(f"Database operational error on close: {e}")
            except sqlite3.Error as e:
                logger.warning(f"Database error on close: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                # 重置单例状态，允许重新初始化
                self.__class__._instance = None
                self.__class__._initialized = False

    def __enter__(self) -> Self:
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器退出，确保连接关闭"""
        self.close()

    def commit(self) -> None:
        """提交事务"""
        self._ensure_conn().commit()

    def execute(self, sql: str, params: tuple | None = None) -> sqlite3.Cursor:
        """执行 SQL 语句

        Args:
            sql: SQL 语句
            params: 参数（可选）

        Returns:
            Cursor 对象
        """
        if params:
            return self._ensure_conn().execute(sql, params)
        return self._ensure_conn().execute(sql)


# 公共导出
__all__ = ["SingletonDB"]