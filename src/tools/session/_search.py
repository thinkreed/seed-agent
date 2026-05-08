"""
搜索方法模块

包含搜索方法：
- search_history, search_with_filters, _fallback_search, _highlight_match, _get_context, _apply_filters
"""

import logging
import sqlite3

from src.tools.fts_utils import sanitize_fts_query
from src.tools.session._search_fts import _fallback_search, search_history
from src.tools.session._search_utils import _apply_filters, _get_context, _highlight_match

logger = logging.getLogger(__name__)


def search_with_filters(
    conn: sqlite3.Connection,
    keyword: str,
    session_id: str | None = None,
    role: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """增强搜索：支持多条件组合"""
    try:
        # 基础查询模板
        SELECT_CLAUSE = """
            SELECT m.id, m.session_id, m.timestamp, m.role, m.content, m.tool_calls_json, m.tool_call_id
            FROM session_messages m
        """
        WHERE_CLAUSE = "WHERE m.message_type = 'message'"

        if keyword.strip():
            fts_query = sanitize_fts_query(keyword)
            if not fts_query:
                return []

            base_sql = f"""{SELECT_CLAUSE}
                JOIN session_messages_fts fts ON m.id = fts.rowid
                {WHERE_CLAUSE}
                AND session_messages_fts MATCH ?
            """
            params = [fts_query]
            order_by = "fts.rank"
        else:
            base_sql = f"{SELECT_CLAUSE} {WHERE_CLAUSE}"
            params = []
            order_by = "m.timestamp DESC"

        base_sql, params = _apply_filters(
            base_sql,
            params,
            session_id,
            role,
            start_time,
            end_time,
            order_by,
            limit,
        )

        rows = conn.execute(base_sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
        return []


__all__ = [
    "_apply_filters",
    "_fallback_search",
    "_get_context",
    "_highlight_match",
    "search_history",
    "search_with_filters",
]