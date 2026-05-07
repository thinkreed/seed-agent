"""
归档数据库 Schema 和连接管理

基于 Hermes Agent FTS5 + WAL 模式设计：
- SQLite + WAL 模式实现高并发
- FTS5 全文索引虚拟表
- jieba 中文分词支持

核心功能：
- 归档主表 (archives)
- 事件详情表 (archive_events)
- FTS5 虚拟表 (archives_fts)
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Self, cast

logger = logging.getLogger(__name__)


def _get_archive_db_path() -> Path:
    """获取归档数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().archives_db
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "memory" / "archives.db"


# Schema 版本
SCHEMA_VERSION = 1


def _create_schema(conn: sqlite3.Connection) -> None:
    """创建数据库 Schema

    Tables:
    - archives: 归档主表
    - archive_events: 事件详情表
    - archives_fts: FTS5 全文索引虚拟表

    Indexes:
    - idx_archives_session: session_id 索引
    - idx_archives_created: created_at 索引
    - idx_events_archive: archive_id 索引
    - idx_events_type: event_type 紧引
    """
    cursor = conn.cursor()

    # 归档主表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archives (
            archive_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            summary TEXT,
            key_findings TEXT,
            events_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            metadata TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archives_session ON archives(session_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_archives_created ON archives(created_at)"
    )

    # 事件详情表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archive_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archive_id TEXT NOT NULL,
            event_id INTEGER,
            event_type TEXT NOT NULL,
            event_data TEXT,
            timestamp REAL,
            FOREIGN KEY (archive_id) REFERENCES archives(archive_id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_archive ON archive_events(archive_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_type ON archive_events(event_type)"
    )

    # FTS5 全文索引虚拟表
    # tokenize='unicode61 remove_diacritics 2' 支持中文
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS archives_fts USING fts5(
            archive_id,
            session_id,
            summary,
            key_findings,
            event_content,
            tokenize='unicode61 remove_diacritics 2',
            prefix='2 3 4'
        )
    """)

    conn.commit()
    logger.info("Archive database schema created/verified")


def _init_connection(db_path: str) -> sqlite3.Connection:
    """初始化数据库连接

    性能优化 PRAGMA:
    - journal_mode=WAL: 写前日志，支持并发
    - synchronous=NORMAL: 减少 fsync 开销
    - busy_timeout=5000: 5 秒等待超时

    Args:
        db_path: 数据库文件路径

    Returns:
        sqlite3.Connection 实例
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # 单例模式允许跨线程访问
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # 性能优化 PRAGMA
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")

    # 创建 Schema
    _create_schema(conn)

    return conn


class ArchiveDBConnection:
    """归档数据库连接管理器

    单例模式，支持跨线程访问。
    """

    _instance: "ArchiveDBConnection | None" = None
    _initialized: bool = False

    def __new__(cls, db_path: str | Path | None = None) -> Self:
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(self, db_path: str | Path | None = None):
        """初始化连接"""
        from threading import Lock

        with Lock():
            if ArchiveDBConnection._initialized:
                return
            ArchiveDBConnection._initialized = True

        self.db_path = str(db_path or _get_archive_db_path())
        self._conn: sqlite3.Connection | None = None
        self._init()

    def _init(self) -> None:
        """初始化数据库连接"""
        self._conn = _init_connection(self.db_path)

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                logger.warning(f"Database close error: {type(e).__name__}: {e}")
            finally:
                self._conn = None
                ArchiveDBConnection._instance = None
                ArchiveDBConnection._initialized = False

    def ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用"""
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        return self._conn

    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return self.ensure_conn()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL"""
        return self.ensure_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """批量执行 SQL"""
        return self.ensure_conn().executemany(sql, params_list)

    def commit(self) -> None:
        """提交事务"""
        self.ensure_conn().commit()