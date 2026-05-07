"""
归档清理和统计

核心功能：
- get_archive_stats: 归档统计信息
- cleanup_old_archives: 清理旧归档
- sync_summary_markers: 摘要标记同步
"""

import datetime as dt_module
import logging
from typing import Any

from ._db_schema import ArchiveDBConnection
from ._fts_search import tokenize_for_fts5

logger = logging.getLogger(__name__)


def get_archive_stats(conn: ArchiveDBConnection) -> dict[str, Any]:
    """获取归档统计

    Returns:
        {
            "total_archives": 归档总数,
            "total_events": 事件总数,
            "avg_events_per_archive": 平均事件数,
            "recent_archives": 最近归档列表
        }
    """
    total_archives = conn.execute(
        "SELECT COUNT(*) as count FROM archives"
    ).fetchone()["count"]

    total_events = conn.execute(
        "SELECT COUNT(*) as count FROM archive_events"
    ).fetchone()["count"]

    avg_events = (
        conn.execute(
            "SELECT AVG(events_count) as avg FROM archives WHERE events_count > 0"
        ).fetchone()["avg"]
        or 0
    )

    recent_archives = conn.execute(
        """
        SELECT archive_id, session_id, summary, created_at, events_count
        FROM archives
        ORDER BY created_at DESC
        LIMIT 5
    """
    ).fetchall()

    return {
        "total_archives": total_archives,
        "total_events": total_events,
        "avg_events_per_archive": round(avg_events, 2),
        "recent_archives": [dict(row) for row in recent_archives],
    }


def cleanup_old_archives(
    conn: ArchiveDBConnection,
    max_age_days: int = 90,
    keep_count: int = 100,
) -> int:
    """清理旧归档

    Args:
        conn: 数据库连接
        max_age_days: 最大保留天数（超过此天数的归档优先删除）
        keep_count: 最少保留数量（即使超过天数也保留此数量）

    Returns:
        清理的归档数量
    """
    from ._archive_operations import delete_archive

    cutoff_date = dt_module.datetime.now(dt_module.UTC) - dt_module.timedelta(days=max_age_days)
    cutoff_str = cutoff_date.isoformat()

    # 检查总数
    total = conn.execute(
        "SELECT COUNT(*) as count FROM archives"
    ).fetchone()["count"]

    if total <= keep_count:
        return 0

    # 计算需要删除的数量
    to_delete = total - keep_count

    # 优先删除超过天数的旧归档
    rows = conn.execute(
        """
        SELECT archive_id FROM archives
        WHERE created_at < ?
        ORDER BY created_at ASC
        LIMIT ?
    """,
        (cutoff_str, to_delete),
    ).fetchall()

    deleted_count = len(rows)

    # 如果删除数量不足，继续删除最旧的归档（确保保留 keep_count）
    if deleted_count < to_delete:
        remaining_to_delete = to_delete - deleted_count
        already_deleted_ids = [row["archive_id"] for row in rows]

        if already_deleted_ids:
            placeholders = ",".join("?" * len(already_deleted_ids))
            additional_rows = conn.execute(
                f"SELECT archive_id FROM archives WHERE archive_id NOT IN ({placeholders}) ORDER BY created_at ASC LIMIT ?",
                (*already_deleted_ids, remaining_to_delete),
            ).fetchall()
        else:
            additional_rows = conn.execute(
                "SELECT archive_id FROM archives ORDER BY created_at ASC LIMIT ?",
                (remaining_to_delete,),
            ).fetchall()

        rows = list(rows) + list(additional_rows)

    # 执行删除
    for row in rows:
        delete_archive(conn, row["archive_id"])

    logger.info(f"Cleaned up {len(rows)} old archives")
    return len(rows)


def sync_summary_markers(
    conn: ArchiveDBConnection,
    event_stream: Any,
) -> str:
    """从事件流同步摘要标记

    Args:
        conn: 数据库连接
        event_stream: SessionEventStream 实例

    Returns:
        同步结果
    """
    # 获取最近的摘要标记
    last_marker = event_stream.find_last_summary_marker()

    if not last_marker:
        return "No summary marker found"

    marker_data = last_marker.get("data", {})
    summary = marker_data.get("summary", "")

    if not summary:
        return "Empty summary in marker"

    session_id = event_stream.session_id

    # 获取会话的归档
    from ._archive_operations import get_archives_by_session

    archives = get_archives_by_session(conn, session_id)

    if archives:
        # 更新最近归档的摘要
        latest_archive_id = archives[0]["archive_id"]
        conn.execute(
            """
            UPDATE archives SET summary = ? WHERE archive_id = ?
        """,
            (summary, latest_archive_id),
        )

        # 更新 FTS 索引
        summary_tokens = tokenize_for_fts5(summary)
        conn.execute(
            """
            UPDATE archives_fts SET summary = ? WHERE archive_id = ?
        """,
            (summary_tokens, latest_archive_id),
        )

        conn.commit()
        return f"Summary synced for archive: {latest_archive_id}"

    return "No archive found for session"