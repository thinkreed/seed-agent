"""
加载操作模块

包含会话历史加载方法：
- load_session_history, _find_session, _format_session_message, list_sessions
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def _find_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    """查找会话（精确匹配后尝试模糊匹配）"""
    row = conn.execute(
        "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if not row:
        row = conn.execute(
            "SELECT session_id, created_at, summary, message_count FROM sessions_meta WHERE session_id LIKE ?",
            (f"%{session_id}%",),
        ).fetchone()
    return row


def _format_session_message(msg: sqlite3.Row) -> str:
    """格式化单条会话消息"""
    role = msg["role"]
    content = msg["content"] or ""

    if msg["tool_calls_json"]:
        try:
            tc_list = json.loads(msg["tool_calls_json"])
            tc_names = [tc.get("function", {}).get("name", "unknown") for tc in tc_list]
            content = f"[Tool Calls: {', '.join(tc_names)}]"
        except Exception as e:
            logger.debug(f"Failed to parse tool_calls_json: {e}")

    if msg["tool_call_id"]:
        content = (msg["content"] or "")[:200]

    if len(content) > 500:
        content = content[:500] + "..."

    return f"{role}: {content}"


def load_session_history(conn: sqlite3.Connection, session_id: str) -> str:
    """从 SQLite 加载指定会话"""
    try:
        row = _find_session(conn, session_id)
        if not row:
            return f"Session not found: {session_id}"

        actual_id = row["session_id"]
        msg_count = row["message_count"]
        # SQLite Row 不支持 .get()，使用 keys() 检查
        summary: str | None = row["summary"] if "summary" in tuple(row.keys()) else None

        messages = conn.execute(
            """
            SELECT role, content, tool_calls_json, tool_call_id
            FROM session_messages
            WHERE session_id = ? AND message_type = 'message'
            ORDER BY id ASC
        """,
            (actual_id,),
        ).fetchall()

        output = f"Session: {actual_id}\n"
        output += f"Created: {row['created_at']}\n"
        output += f"Messages: {msg_count}\n"
        if summary:
            output += f"Summary: {summary}\n"
        output += "---\n"

        for msg in messages:
            output += _format_session_message(msg) + "\n"

        return output
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error loading session")
        return f"Error loading session (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error loading session")
        return f"Error loading session: {type(e).__name__}: {e!s}"


def list_sessions(conn: sqlite3.Connection, limit: int = 10) -> str:
    """列出最近会话"""
    try:
        sessions = conn.execute(
            """
            SELECT session_id, created_at, last_updated, message_count, summary
            FROM sessions_meta
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()

        if not sessions:
            return "No sessions found."

        output = "Recent Sessions:\n"
        for s in sessions:
            output += f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
            if s["summary"]:
                summary_text = s["summary"][:100] if s["summary"] else ""
                if summary_text:
                    output += f"  Summary: {summary_text}...\n"

        return output
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error listing sessions")
        return f"Error listing sessions (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error listing sessions")
        return f"Error listing sessions: {type(e).__name__}: {e!s}"


__all__ = [
    "_find_session",
    "_format_session_message",
    "list_sessions",
    "load_session_history",
]
