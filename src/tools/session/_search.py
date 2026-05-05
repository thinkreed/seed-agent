"""
搜索方法模块

包含搜索方法：
- search_history, search_with_filters, _fallback_search, _highlight_match, _get_context, _apply_filters
"""

import logging
import sqlite3

from src.tools.fts_utils import sanitize_fts_query

logger = logging.getLogger(__name__)


def _highlight_match(content: str, keyword: str, max_len: int = 300) -> str:
    """高亮匹配部分"""
    if not content:
        return ""

    idx = content.lower().find(keyword.lower())
    if idx == -1:
        return content[:max_len] + ("..." if len(content) > max_len else "")

    start = max(0, idx - 50)
    end = min(len(content), idx + len(keyword) + 250)
    preview = content[start:end]
    if start > 0:
        preview = "..." + preview
    if end < len(content):
        preview = preview + "..."

    return preview


def _get_context(
    conn: sqlite3.Connection, session_id: str, msg_id: int, context_size: int = 1
) -> list[str]:
    """获取消息的上下文"""
    try:
        context_msgs = conn.execute(
            """
            SELECT role, content
            FROM session_messages
            WHERE session_id = ? AND message_type = 'message'
            AND id BETWEEN ? AND ?
            ORDER BY id ASC
        """,
            (session_id, msg_id - context_size, msg_id + context_size),
        ).fetchall()

        return [f"{m['role']}: {(m['content'] or '')[:100]}" for m in context_msgs]
    except Exception as e:
        logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
        return []


def _apply_filters(
    base_sql: str,
    params: list,
    session_id: str | None,
    role: str | None,
    start_time: str | None,
    end_time: str | None,
    order_by: str,
    limit: int,
) -> tuple[str, list]:
    """添加通用过滤条件到 SQL 查询"""
    if session_id:
        base_sql += " AND m.session_id = ?"
        params.append(session_id)
    if role:
        base_sql += " AND m.role = ?"
        params.append(role)
    if start_time:
        base_sql += " AND m.timestamp >= ?"
        params.append(start_time)
    if end_time:
        base_sql += " AND m.timestamp <= ?"
        params.append(end_time)

    base_sql += f" ORDER BY {order_by} LIMIT ?"
    params.append(limit)
    return base_sql, params


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
