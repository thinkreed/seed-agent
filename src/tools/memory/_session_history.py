"""
会话历史管理 - SQLite + FTS5 后端 (wrapper)

优先使用 session_db.py 的 SQLite 实现，fallback 到 JSONL。

核心功能：
- _save_session_history: 保存会话历史
- _load_session_history: 加载会话历史
- _list_sessions: 列出会话
- _search_history: 搜索历史 (FTS5)
"""

import logging

from ._session_history_jsonl import (
    _list_sessions_jsonl,
    _load_session_history_jsonl,
    _save_session_history_jsonl,
    _search_history_jsonl,
)

logger = logging.getLogger(__name__)


def _save_session_history(
    messages: list, summary: str | None = None, session_id: str | None = None
) -> str:
    """Save conversation history to SQLite (wrapper for session_db.py)

    Args:
        messages: 消息列表
        summary: 会话摘要
        session_id: 会话 ID（可选）

    Returns:
        状态信息
    """
    try:
        from src.tools.session_db import save_session_history as sqlite_save

        return sqlite_save(messages, summary, session_id)
    except ImportError:
        logger.debug("session_db not available, using JSONL fallback")
        return _save_session_history_jsonl(messages, summary, session_id)


def _load_session_history(session_id: str) -> str:
    """Load conversation history from SQLite (wrapper for session_db.py)

    Args:
        session_id: 会话 ID

    Returns:
        会话内容
    """
    try:
        from src.tools.session_db import load_session_history as sqlite_load

        return sqlite_load(session_id)
    except ImportError:
        logger.debug("session_db not available, using JSONL fallback")
        return _load_session_history_jsonl(session_id)


def _list_sessions(limit: int = 10) -> str:
    """List recent sessions from SQLite (wrapper for session_db.py)

    Args:
        limit: 最大返回数量

    Returns:
        会话列表
    """
    try:
        from src.tools.session_db import list_sessions as sqlite_list

        return sqlite_list(limit)
    except ImportError:
        logger.debug("session_db not available, using JSONL fallback")
        return _list_sessions_jsonl(limit)


def _search_history(keyword: str, limit: int = 20) -> str:
    """Search conversation history using FTS5 (wrapper for session_db.py)

    Args:
        keyword: 搜索关键词
        limit: 最大返回数量

    Returns:
        匹配的消息列表
    """
    try:
        from src.tools.session_db import search_history as sqlite_search

        return sqlite_search(keyword, limit)
    except ImportError:
        logger.debug("session_db not available, using JSONL fallback")
        return _search_history_jsonl(keyword, limit)