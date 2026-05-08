"""
归档读取操作

核心功能：
- get_archive: 获取完整归档
- get_archives_by_session: 获取会话的所有归档
- delete_archive: 删除归档
"""

import json
from typing import Any

from ._db_schema import ArchiveDBConnection


def get_archive(conn: ArchiveDBConnection, archive_id: str) -> dict[str, Any] | None:
    """获取完整归档

    Args:
        conn: 数据库连接
        archive_id: 归档 ID

    Returns:
        归档完整信息，包括事件列表
    """
    row = conn.execute(
        """
        SELECT archive_id, session_id, summary, key_findings, created_at, events_count, metadata
        FROM archives
        WHERE archive_id = ?
        """,
        (archive_id,),
    ).fetchone()

    if not row:
        return None

    # 获取事件详情
    event_rows = conn.execute(
        """
        SELECT event_id, event_type, event_data, timestamp
        FROM archive_events
        WHERE archive_id = ?
        ORDER BY event_id
        """,
        (archive_id,),
    ).fetchall()

    events = [
        {
            "id": er["event_id"],
            "type": er["event_type"],
            "data": json.loads(er["event_data"] or "{}"),
            "timestamp": er["timestamp"],
        }
        for er in event_rows
    ]

    return {
        "archive_id": row["archive_id"],
        "session_id": row["session_id"],
        "summary": row["summary"],
        "key_findings": json.loads(row["key_findings"] or "[]"),
        "created_at": row["created_at"],
        "events_count": row["events_count"],
        "metadata": json.loads(row["metadata"] or "{}"),
        "events": events,
    }


def get_archives_by_session(
    conn: ArchiveDBConnection, session_id: str
) -> list[dict[str, Any]]:
    """获取会话的所有归档

    Args:
        conn: 数据库连接
        session_id: 会话 ID

    Returns:
        归档列表
    """
    rows = conn.execute(
        """
        SELECT archive_id, session_id, summary, created_at, events_count
        FROM archives
        WHERE session_id = ?
        ORDER BY created_at DESC
        """,
        (session_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def delete_archive(conn: ArchiveDBConnection, archive_id: str) -> str:
    """删除归档

    Args:
        conn: 数据库连接
        archive_id: 归档 ID

    Returns:
        状态信息
    """
    conn.execute("DELETE FROM archive_events WHERE archive_id = ?", (archive_id,))
    conn.execute("DELETE FROM archives_fts WHERE archive_id = ?", (archive_id,))
    conn.execute("DELETE FROM archives WHERE archive_id = ?", (archive_id,))
    conn.commit()
    return f"Archive deleted: {archive_id}"