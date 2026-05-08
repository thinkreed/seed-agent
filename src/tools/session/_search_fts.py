"""
FTS 搜索方法模块

包含 FTS5 全文搜索方法：
- search_history: FTS5 全文搜索
- _fallback_search: 简单字符串匹配搜索
"""

import logging
import sqlite3

from src.tools.fts_utils import sanitize_fts_query
from src.tools.session._search_utils import _get_context, _highlight_match

logger = logging.getLogger(__name__)


def _fallback_search(conn: sqlite3.Connection, keyword: str, limit: int = 20) -> str:
    """简单的字符串匹配搜索"""
    try:
        results = conn.execute(
            """
            SELECT session_id, timestamp, role, content, id as msg_id
            FROM session_messages
            WHERE content LIKE ? AND message_type = 'message'
            LIMIT ?
        """,
            (f"%{keyword}%", limit),
        ).fetchall()

        if not results:
            return f"No matches found for: {keyword}"

        output = f"Found {len(results)} matches for '{keyword}':\n"
        for r in results:
            content = r["content"] or ""
            matched_preview = _highlight_match(content, keyword)
            context = _get_context(conn, r["session_id"], r["msg_id"], 1)
            output += f"\n[{r['session_id']}] {r['timestamp']}\n"
            output += f"{r['role']}: {matched_preview}\n"
            output += f"Context: {context}\n"

        return output
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error in fallback search")
        return f"Error in fallback search (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error in fallback search")
        return f"Error in fallback search: {type(e).__name__}: {e!s}"


def search_history(conn: sqlite3.Connection, keyword: str, limit: int = 20) -> str:
    """使用 FTS5 全文搜索"""
    try:
        if not keyword.strip():
            return "Please provide a search keyword."

        fts_query = sanitize_fts_query(keyword)
        if not fts_query:
            return f"No matches found for: {keyword}"

        query_expr = fts_query

        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in fts_query)

        if has_cjk:
            tokens = fts_query.split()
            if len(tokens) > 1:
                query_expr = " OR ".join(tokens)

        results = conn.execute(
            """
            SELECT
                m.session_id, m.timestamp, m.role, m.content, m.tool_call_id,
                m.id as msg_id
            FROM session_messages m
            JOIN session_messages_fts fts ON m.id = fts.rowid
            WHERE session_messages_fts MATCH ?
            AND m.message_type = 'message'
            ORDER BY fts.rank
            LIMIT ?
        """,
            (query_expr, limit),
        ).fetchall()

        if not results:
            return _fallback_search(conn, keyword, limit)

        output = f"Found {len(results)} matches for '{keyword}':\n"
        for r in results:
            content = r["content"] or ""
            matched_preview = _highlight_match(content, keyword)
            context = _get_context(conn, r["session_id"], r["msg_id"], 1)

            output += f"\n[{r['session_id']}] {r['timestamp']}\n"
            output += f"{r['role']}: {matched_preview}\n"
            output += f"Context: {context}\n"

        return output
    except sqlite3.OperationalError as e:
        logger.debug(f"FTS search failed, falling back to LIKE search: {e}")
        return _fallback_search(conn, keyword, limit)
    except sqlite3.DatabaseError as e:
        logger.exception("Database error searching history")
        return f"Error searching history (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error searching history")
        return f"Error searching history: {type(e).__name__}: {e!s}"


__all__ = ["_fallback_search", "search_history"]