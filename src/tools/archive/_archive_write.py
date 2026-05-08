"""
归档写入操作

核心功能：
- store_events: 批量存储事件详情
- archive_session: 归档会话事件流
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from ._db_schema import ArchiveDBConnection
from ._fts_search import tokenize_for_fts5
from ._archive_fts import build_event_content_for_fts

logger = logging.getLogger(__name__)


def store_events(
    conn: ArchiveDBConnection, archive_id: str, events: list[dict[str, Any]]
) -> None:
    """存储事件详情 - 使用批量插入优化

    Args:
        conn: 数据库连接
        archive_id: 归档 ID
        events: 事件列表
    """
    if not events:
        return

    batch_data = [
        (
            archive_id,
            event.get("id", 0),
            event.get("type", "unknown"),
            json.dumps(event.get("data", {}), ensure_ascii=False),
            event.get("timestamp", 0),
        )
        for event in events
    ]

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

    Args:
        conn: 数据库连接
        session_id: 会话 ID
        events: 事件列表
        summary: 摘要内容
        key_findings: 关键发现列表
        metadata: 可选元数据

    Returns:
        archive_id 或错误信息
    """
    if not events:
        return "Error: No events to archive"

    archive_id = f"archive_{session_id}_{int(time.time())}"
    created_at = datetime.now(UTC).isoformat()

    # 存储归档主记录
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
            json.dumps(key_findings, ensure_ascii=False),
            len(events),
            created_at,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )

    # 存储事件详情
    store_events(conn, archive_id, events)

    # 更新 FTS5 索引
    event_content = build_event_content_for_fts(events)
    key_findings_text = " ".join(key_findings)

    conn.execute(
        """
        INSERT INTO archives_fts
            (archive_id, session_id, summary, key_findings, event_content)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            archive_id,
            session_id,
            tokenize_for_fts5(summary),
            tokenize_for_fts5(key_findings_text),
            tokenize_for_fts5(event_content),
        ),
    )

    conn.commit()
    logger.info(f"Session archived: {archive_id} ({len(events)} events)")
    return archive_id