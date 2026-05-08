"""SessionDB 类实现 - SQLite + FTS5 + Memory Graph 数据库管理"""

import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Self, cast

from src.tools.session._cleanup import (
    cleanup_old_outcomes, get_session_stats, optimize_index, rebuild_index,
)
from src.tools.session._load import list_sessions, load_session_history
from src.tools.session._save import save_session_history
from src.tools.session._schema import create_schema
from src.tools.session._search import search_history, search_with_filters
from src.tools.session._skill_outcomes import (
    BannedSkillInfo, get_skill_stats, get_top_skills, list_banned_skills,
    record_skill_outcome, search_outcomes_by_signal,
)

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """获取数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return str(get_paths_config().sessions_db)
    except RuntimeError:
        return os.path.join(os.path.expanduser("~"), ".seed", "memory", "raw", "sessions.db")


class SessionDB:
    """Session 数据库管理类 (SQLite + FTS5 + Memory Graph)，支持单例模式、线程安全."""

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
        self.db_path = db_path or get_db_path()
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
        create_schema(self.conn)

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

    def save_session_history(self, messages: list[dict], summary: str | None = None,
                            session_id: str | None = None) -> str:
        return save_session_history(self._ensure_conn(), messages, summary,
                                    session_id, self._generate_session_filename)

    def load_session_history(self, session_id: str) -> str:
        return load_session_history(self._ensure_conn(), session_id)

    def list_sessions(self, limit: int = 10) -> str:
        return list_sessions(self._ensure_conn(), limit)

    def search_history(self, keyword: str, limit: int = 20) -> str:
        return search_history(self._ensure_conn(), keyword, limit)

    def search_with_filters(self, keyword: str, session_id: str | None = None,
                            role: str | None = None, start_time: str | None = None,
                            end_time: str | None = None, limit: int = 20) -> list[dict]:
        return search_with_filters(self._ensure_conn(), keyword, session_id,
                                   role, start_time, end_time, limit)

    def record_skill_outcome(self, skill_name: str, outcome: str, score: float = 1.0,
                            signals: list[str] | None = None, session_id: str | None = None,
                            context: str | None = None, intent: str | None = None,
                            blast_radius: dict | None = None) -> str:
        return record_skill_outcome(self._ensure_conn(), skill_name, outcome,
                                    score, signals, session_id, context, intent, blast_radius)

    def get_skill_stats(self, skill_name: str) -> dict:
        return get_skill_stats(self._ensure_conn(), skill_name)

    def list_banned_skills(self) -> list[BannedSkillInfo]:
        return list_banned_skills(self._ensure_conn())

    def get_top_skills(self, limit: int = 10) -> list[dict]:
        return get_top_skills(self._ensure_conn(), limit)

    def search_outcomes_by_signal(self, signal: str, limit: int = 20) -> list[dict]:
        return search_outcomes_by_signal(self._ensure_conn(), signal, limit)

    def cleanup_old_outcomes(self, max_entries_per_skill: int | None = None) -> int:
        return cleanup_old_outcomes(self._ensure_conn(), max_entries_per_skill)

    def optimize_index(self) -> str:
        return optimize_index(self._ensure_conn())

    def rebuild_index(self) -> str:
        return rebuild_index(self._ensure_conn())

    def get_session_stats(self, session_id: str) -> dict:
        return get_session_stats(self._ensure_conn(), session_id)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception as e:
            logger.debug(f"Exception during __del__ cleanup: {e}")