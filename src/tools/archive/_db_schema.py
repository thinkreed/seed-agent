"""
归档数据库 Schema 和连接管理

基于 Hermes Agent FTS5 + WAL 模式：
- SQLite + WAL 高并发
- FTS5 全文索引 + jieba 中文分词
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
        return Path.home() / ".seed" / "memory" / "archives.db"


SCHEMA_VERSION = 1


def _create_schema(conn: sqlite3.Connection) -> None:
    """创建归档数据库 Schema（archives 主表、archive_events 事件表、archives_fts 全文索引）"""
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_archives_session ON archives(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_archives_created ON archives(created_at)")

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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_archive ON archive_events(archive_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON archive_events(event_type)")

    # FTS5 全文索引虚拟表（unicode61 支持中文）
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS archives_fts USING fts5(
            archive_id, session_id, summary, key_findings, event_content,
            tokenize='unicode61 remove_diacritics 2',
            prefix='2 3 4'
        )
    """)

    conn.commit()
    logger.info("Archive database schema created/verified")


def _init_connection(db_path: str) -> sqlite3.Connection:
    """初始化数据库连接（WAL模式 + 性能优化 PRAGMA）"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 性能优化 PRAGMA
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    _create_schema(conn)
    return conn


class ArchiveDBConnection:
    """归档数据库连接管理器（单例模式，跨线程访问）"""

    _instance: "ArchiveDBConnection | None" = None
    _initialized: bool = False

    def __new__(cls, db_path: str | Path | None = None) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(self, db_path: str | Path | None = None):
        from threading import Lock
        with Lock():
            if ArchiveDBConnection._initialized:
                return
            ArchiveDBConnection._initialized = True
        self.db_path = str(db_path or _get_archive_db_path())
        self._conn: sqlite3.Connection | None = None
        self._init()

    def _init(self) -> None:
        self._conn = _init_connection(self.db_path)

    def close(self) -> None:
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
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        return self._conn

    def get_connection(self) -> sqlite3.Connection:
        return self.ensure_conn()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.ensure_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        return self.ensure_conn().executemany(sql, params_list)

    def commit(self) -> None:
        self.ensure_conn().commit()