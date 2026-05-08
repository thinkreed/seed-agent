"""
归档统计信息

提取 get_archive_stats 函数。
"""

from typing import Any

from ._db_schema import ArchiveDBConnection


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


__all__ = ["get_archive_stats"]