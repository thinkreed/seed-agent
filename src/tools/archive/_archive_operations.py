"""
归档操作 - 存储和检索

核心功能：
- archive_session: 归档会话事件流
- get_archive: 获取完整归档
- get_archives_by_session: 获取会话的所有归档
- store_events: 批量存储事件详情
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from ._db_schema import ArchiveDBConnection
from ._fts_search import tokenize_for_fts5

logger = logging.getLogger(__name__)


def _build_event_content_for_fts(events: list[dict[str, Any]]) -> str:
    """构建事件内容文本用于 FTS"""
    content_parts = []

    for event in events:
        event_type = event.get("type", "")
        event_data = event.get("data", {})

        if event_type == "user_input":
            content_parts.append(event_data.get("content", ""))
        elif event_type == "llm_response":
            content_parts.append(event_data.get("content", "")[:500])
        elif event_type == "tool_result":
            content_parts.append(event_data.get("content", "")[:200])

    return " ".join(content_parts)


def store_events(
    conn: ArchiveDBConnection, archive_id: str, events: list[dict[str, Any]]
) -> None:
    """存储事件详情 - 使用批量插入优化"""
    if not events:
        return

    # 构建批量数据
    batch_data = []
    for event in events:
        event_data_json = json.dumps(event.get("data", {}), ensure_ascii=False)
        batch_data.append(
            (
                archive_id,
                event.get("id", 0),
                event.get("type", "unknown"),
                event_data_json,
                event.get("timestamp", 0),
            )
        )

    # 执行批量插入
    conn.executemany(
        """
        INSERT INTO archive_events
            (archive_id, event_id, event_type, event_data, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """,
        batch_data,
    )


async def archive_session(
    conn: ArchiveDBConnection,
    session_id: str,
    events: list[dict[str, Any]],
    summary: str,
    key_findings: list[str],
    metadata: dict[str, Any] | None = None,
) -> str:
    """归档会话

    流程:
    1. 存储归档主记录
    2. 存储事件详情
    3. 更新 FTS5 索引

    Args:
        conn: 数据库连接
        session_id: 会话 ID
        events: 事件列表
        summary: 摘要内容
        key_findings: 关键发现列表
        metadata: 可选元数据

    Returns:
        archive_id
    """
    if not events:
        return "Error: No events to archive"

    archive_id = f"archive_{session_id}_{int(time.time())}"
    created_at = datetime.now(UTC).isoformat()

    # 存储归档主记录
    key_findings_json = json.dumps(key_findings, ensure_ascii=False)
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO archives
            (archive_id, session_id, summary, key_findings, events_count, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            archive_id,
            session_id,
            summary,
            key_findings_json,
            len(events),
            created_at,
            metadata_json,
        ),
    )

    # 存储事件详情
    store_events(conn, archive_id, events)

    # 更新 FTS5 索引
    event_content = _build_event_content_for_fts(events)
    key_findings_text = " ".join(key_findings)

    # 使用 tokenize_for_fts5 进行分词预处理
    summary_tokens = tokenize_for_fts5(summary)
    key_findings_tokens = tokenize_for_fts5(key_findings_text)
    event_content_tokens = tokenize_for_fts5(event_content)

    conn.execute(
        """
        INSERT INTO archives_fts
            (archive_id, session_id, summary, key_findings, event_content)
        VALUES (?, ?, ?, ?, ?)
    """,
        (archive_id, session_id, summary_tokens, key_findings_tokens, event_content_tokens),
    )

    conn.commit()

    logger.info(f"Session archived: {archive_id} ({len(events)} events)")
    return archive_id


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
    # 删除事件
    conn.execute(
        "DELETE FROM archive_events WHERE archive_id = ?", (archive_id,)
    )

    # 删除 FTS 索引
    conn.execute(
        "DELETE FROM archives_fts WHERE archive_id = ?", (archive_id,)
    )

    # 删除归档记录
    conn.execute(
        "DELETE FROM archives WHERE archive_id = ?", (archive_id,)
    )

    conn.commit()
    return f"Archive deleted: {archive_id}"