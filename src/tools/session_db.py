"""
L4 Session 数据库存储层 (SQLite + FTS5)
替代原有的 JSONL 文件存储，支持中文全文搜索

使用 jieba 进行中文分词预处理，通过 FTS5 实现高效搜索。

Memory Graph 增强:
- gene_outcomes 表: 存储 Skill 执行结果
- FTS5 虚拟表: 信号模式全文搜索
- 选择算法支持: 成功率统计、禁用阈值、Laplace 平滑

模块结构:
- session_db.py: SessionDB 类骨架 + 模块级公共函数
- session/_schema.py: Schema 创建方法
- session/_skill_outcomes.py: Skill 结果方法
- session/_save.py: 保存操作
- session/_load.py: 加载操作
- session/_search.py: 搜索方法
- session/_cleanup.py: 清理方法
"""

import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, cast

from src.tools.fts_utils import sanitize_fts_query as _sanitize_fts_query
from src.tools.fts_utils import tokenize_for_fts5
from src.tools.session._cleanup import cleanup_old_outcomes as _cleanup_old_outcomes
from src.tools.session._cleanup import get_session_stats as _get_session_stats_impl
from src.tools.session._cleanup import optimize_index as _optimize_index_impl
from src.tools.session._cleanup import rebuild_index as _rebuild_index_impl
from src.tools.session._load import list_sessions as _list_sessions_impl
from src.tools.session._load import load_session_history as _load_session_history_impl
from src.tools.session._save import save_session_history as _save_session_history_impl
from src.tools.session._schema import create_schema as _create_schema_impl
from src.tools.session._search import search_history as _search_history_impl
from src.tools.session._search import search_with_filters as _search_with_filters_impl
from src.tools.session._skill_outcomes import BannedSkillInfo
from src.tools.session._skill_outcomes import get_skill_stats as _get_skill_stats_impl
from src.tools.session._skill_outcomes import get_top_skills as _get_top_skills_impl
from src.tools.session._skill_outcomes import (
    list_banned_skills as _list_banned_skills_impl,
)
from src.tools.session._skill_outcomes import (
    record_skill_outcome as _record_skill_outcome_impl,
)
from src.tools.session._skill_outcomes import (
    search_outcomes_by_signal as _search_outcomes_by_signal_impl,
)

logger = logging.getLogger(__name__)


def _get_db_path() -> Path:
    """获取数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().sessions_db
    except RuntimeError:
        return Path.home() / ".seed" / "memory" / "raw" / "sessions.db"


DB_PATH = None  # 类型: Path | None


def _ensure_db_path() -> Path:
    """确保数据库路径已初始化"""
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = _get_db_path()
    return DB_PATH


class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5 + Memory Graph)

    支持上下文管理器协议，确保资源正确释放。
    使用单例模式防止多连接资源泄漏。
    使用线程锁保证多线程环境下的线程安全。
    """

    _instance: "SessionDB | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | None = None) -> Self:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(self, db_path: str | None = None):
        with SessionDB._lock:
            if SessionDB._initialized:
                return
            SessionDB._initialized = True
        self.db_path = db_path or str(_ensure_db_path())
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-32000;")
        _create_schema_impl(self.conn)

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.OperationalError as e:
                logger.warning(f"Database operational error on close: {e}")
            except sqlite3.Error as e:
                logger.warning(f"Database error on close: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                SessionDB._instance = None
                SessionDB._initialized = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _ensure_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def _generate_session_filename(self) -> str:
        return f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.jsonl"

    # Session 方法
    def save_session_history(self, messages: list[dict], summary: str | None = None,
                            session_id: str | None = None) -> str:
        return _save_session_history_impl(self._ensure_conn(), messages, summary,
                                          session_id, self._generate_session_filename)

    def load_session_history(self, session_id: str) -> str:
        return _load_session_history_impl(self._ensure_conn(), session_id)

    def list_sessions(self, limit: int = 10) -> str:
        return _list_sessions_impl(self._ensure_conn(), limit)

    def search_history(self, keyword: str, limit: int = 20) -> str:
        return _search_history_impl(self._ensure_conn(), keyword, limit)

    def search_with_filters(self, keyword: str, session_id: str | None = None,
                            role: str | None = None, start_time: str | None = None,
                            end_time: str | None = None, limit: int = 20) -> list[dict]:
        return _search_with_filters_impl(self._ensure_conn(), keyword, session_id,
                                         role, start_time, end_time, limit)

    # Memory Graph 方法
    def record_skill_outcome(self, skill_name: str, outcome: str, score: float = 1.0,
                            signals: list[str] | None = None, session_id: str | None = None,
                            context: str | None = None, intent: str | None = None,
                            blast_radius: dict | None = None) -> str:
        return _record_skill_outcome_impl(self._ensure_conn(), skill_name, outcome,
                                          score, signals, session_id, context, intent, blast_radius)

    def get_skill_stats(self, skill_name: str) -> dict:
        return _get_skill_stats_impl(self._ensure_conn(), skill_name)

    def list_banned_skills(self) -> list[BannedSkillInfo]:
        return _list_banned_skills_impl(self._ensure_conn())

    def get_top_skills(self, limit: int = 10) -> list[dict]:
        return _get_top_skills_impl(self._ensure_conn(), limit)

    def search_outcomes_by_signal(self, signal: str, limit: int = 20) -> list[dict]:
        return _search_outcomes_by_signal_impl(self._ensure_conn(), signal, limit)

    # 清理方法
    def cleanup_old_outcomes(self, max_entries_per_skill: int | None = None) -> int:
        return _cleanup_old_outcomes(self._ensure_conn(), max_entries_per_skill)

    def optimize_index(self) -> str:
        return _optimize_index_impl(self._ensure_conn())

    def rebuild_index(self) -> str:
        return _rebuild_index_impl(self._ensure_conn())

    def get_session_stats(self, session_id: str) -> dict:
        return _get_session_stats_impl(self._ensure_conn(), session_id)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as e:
            logger.debug(f"Exception during __del__ cleanup: {e}")


# 模块级便捷函数
_db_instance: SessionDB | None = None
_db_lock = threading.Lock()


def _get_db() -> SessionDB:
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = SessionDB()
    return _db_instance


def save_session_history(messages: list, summary: str | None = None,
                         session_id: str | None = None) -> str:
    return _get_db().save_session_history(messages, summary, session_id)


def load_session_history(session_id: str) -> str:
    return _get_db().load_session_history(session_id)


def list_sessions(limit: int = 10) -> str:
    return _get_db().list_sessions(limit)


def search_history(keyword: str, limit: int = 20) -> str:
    return _get_db().search_history(keyword, limit)


def record_skill_outcome(skill_name: str, outcome: str, score: float = 1.0,
                         signals: list[str] | None = None, session_id: str | None = None,
                         context: str | None = None) -> str:
    return _get_db().record_skill_outcome(skill_name, outcome, score, signals, session_id, context)


def get_skill_stats(skill_name: str) -> dict:
    return _get_db().get_skill_stats(skill_name)


def list_banned_skills() -> list[BannedSkillInfo]:
    return _get_db().list_banned_skills()


def get_top_skills(limit: int = 10) -> list[dict]:
    return _get_db().get_top_skills(limit)


def search_outcomes_by_signal(signal: str, limit: int = 20) -> list[dict]:
    return _get_db().search_outcomes_by_signal(signal, limit)


__all__ = [
    "BannedSkillInfo",
    "SessionDB",
    "_ensure_db_path",
    "_get_db_path",
    "_sanitize_fts_query",
    "get_skill_stats",
    "get_top_skills",
    "list_banned_skills",
    "list_sessions",
    "load_session_history",
    "record_skill_outcome",
    "save_session_history",
    "search_history",
    "search_outcomes_by_signal",
    "tokenize_for_fts5",
]
