"""
保存操作模块

包含会话历史保存方法：
- save_session_history, _build_message_batches, _insert_fts_index, _upsert_session_meta
"""

import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from src.tools.fts_utils import tokenize_for_fts5

logger = logging.getLogger(__name__)


def _parse_tool_calls(tool_calls) -> str | None:
    """序列化 tool_calls 为 JSON"""
    if tool_calls:
        return json.dumps(tool_calls, ensure_ascii=False)
    return None


def _build_message_batches(
    messages: list[dict], session_id: str, now: str
) -> tuple[list[tuple], list[tuple]]:
    """构建消息批次 (session_messages + FTS)"""
    batch = []
    fts_batch = []
    for msg in messages:
        ts = msg.get("timestamp", now)
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        tool_calls = _parse_tool_calls(msg.get("tool_calls"))
        tool_call_id = msg.get("tool_call_id")

        batch.append(
            (session_id, ts, role, content, tool_calls, tool_call_id, "message")
        )
        tokenized = tokenize_for_fts5(content) if content else ""
        fts_batch.append((session_id, tokenized, role))
    return batch, fts_batch


def _insert_fts_index(
    cursor: sqlite3.Cursor, fts_batch: list[tuple], start_id: int
) -> None:
    """插入 FTS 索引 - 使用批量插入优化"""
    if not fts_batch:
        return

    # 构建批量数据
    batch_data = []
    for i, (sid, tokenized, role) in enumerate(fts_batch):
        rowid = start_id + i
        batch_data.append((rowid, tokenized, sid, role))

    # 执行批量插入
    cursor.executemany(
        "INSERT INTO session_messages_fts(rowid, content, session_id, role) VALUES (?, ?, ?, ?)",
        batch_data,
    )


def _upsert_session_meta(
    cursor: sqlite3.Cursor,
    session_id: str,
    now: str,
    msg_count: int,
    summary: str | None,
    is_new: bool,
) -> None:
    """插入或更新会话元数据"""
    if is_new:
        cursor.execute(
            "INSERT INTO sessions_meta "
            "(session_id, created_at, last_updated, message_count, summary) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, now, now, msg_count, summary),
        )
    else:
        cursor.execute(
            "UPDATE sessions_meta SET last_updated = ?, "
            "message_count = message_count + ?, "
            "summary = COALESCE(?, summary) WHERE session_id = ?",
            (now, msg_count, summary, session_id),
        )


def save_session_history(
    conn: sqlite3.Connection,
    messages: list[dict],
    summary: str | None = None,
    session_id: str | None = None,
    generate_session_filename: Callable[[], str] | None = None,
) -> str:
    """保存会话历史到 SQLite

    Args:
        conn: 数据库连接
        messages: 会话消息列表
        summary: 会话摘要
        session_id: 会话 ID（可选）
        generate_session_filename: 生成会话文件名的函数
    """
    try:
        if not session_id:
            if generate_session_filename:
                session_id = generate_session_filename()
            else:
                timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                session_id = f"session_{timestamp}.jsonl"

        now = datetime.now(UTC).isoformat()

        existing = conn.execute(
            "SELECT session_id FROM sessions_meta WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        is_new = existing is None

        cursor = conn.cursor()
        batch, fts_batch = _build_message_batches(messages, session_id, now)

        cursor.executemany(
            "INSERT INTO session_messages "
            "(session_id, timestamp, role, content, tool_calls_json, "
            " tool_call_id, message_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            batch,
        )

        if batch:
            # executemany doesn't set lastrowid, so query for it
            start_id = (
                cursor.execute("SELECT MAX(id) FROM session_messages").fetchone()[0]
                - len(batch)
                + 1
            )
            _insert_fts_index(cursor, fts_batch, start_id)

        msg_count = len(messages)
        _upsert_session_meta(cursor, session_id, now, msg_count, summary, is_new)

        conn.commit()
        return f"Session saved: {session_id} ({msg_count} messages)"
    except sqlite3.OperationalError as e:
        conn.rollback()
        logger.exception("Database operational error saving session")
        return f"Error saving session (database issue): {e!s}"
    except sqlite3.IntegrityError as e:
        conn.rollback()
        logger.exception("Database integrity error saving session")
        return f"Error saving session (integrity issue): {e!s}"
    except Exception as e:
        conn.rollback()
        logger.exception("Unexpected error saving session")
        return f"Error saving session: {type(e).__name__}: {e!s}"


__all__ = [
    "_build_message_batches",
    "_insert_fts_index",
    "_parse_tool_calls",
    "_upsert_session_meta",
    "save_session_history",
]
