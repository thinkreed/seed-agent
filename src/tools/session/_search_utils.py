"""
搜索工具函数模块

包含搜索辅助函数：
- _highlight_match: 高亮匹配部分
- _get_context: 获取消息上下文
- _apply_filters: 添加过滤条件
"""

import logging
import sqlite3

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


__all__ = ["_highlight_match", "_get_context", "_apply_filters"]