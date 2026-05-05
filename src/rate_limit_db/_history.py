"""请求历史操作

查询、清理请求历史
"""

import logging
import time
from typing import Any

from ._connection import DatabaseConnection

logger = logging.getLogger("seed_agent")


async def cleanup_old_history(
    db_conn: DatabaseConnection, max_age: float = 86400.0
) -> int:
    """清理过期历史记录

    Args:
        db_conn: 数据库连接管理器
        max_age: 最大保留时间（秒），默认 24 小时

    Returns:
        清理的记录数
    """
    async with db_conn.get_lock():
        conn = db_conn.get_connection()
        cutoff = time.time() - max_age
        cursor = conn.execute(
            """
            DELETE FROM request_history WHERE timestamp < ?
        """,
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted


async def get_recent_requests(
    db_conn: DatabaseConnection, limit: int = 100
) -> list[dict[str, Any]]:
    """获取最近的请求历史

    Args:
        db_conn: 数据库连接管理器
        limit: 结果限制

    Returns:
        请求历史列表
    """
    async with db_conn.get_lock():
        conn = db_conn.get_connection()
        cursor = conn.execute(
            """
            SELECT request_id, timestamp, priority, duration, success, error_message
            FROM request_history
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (limit,),
        )
        rows = cursor.fetchall()

        return [
            {
                "request_id": row[0],
                "timestamp": row[1],
                "priority": row[2],
                "duration": row[3],
                "success": bool(row[4]),
                "error_message": row[5],
            }
            for row in rows
        ]


async def get_stats(db_conn: DatabaseConnection) -> dict[str, Any]:
    """获取统计信息

    Args:
        db_conn: 数据库连接管理器

    Returns:
        统计信息字典
    """
    async with db_conn.get_lock():
        conn = db_conn.get_connection()

        # 总请求数
        cursor = conn.execute("SELECT COUNT(*) FROM request_history")
        total_requests = cursor.fetchone()[0]

        # 成功请求数
        cursor = conn.execute(
            "SELECT COUNT(*) FROM request_history WHERE success = 1"
        )
        successful_requests = cursor.fetchone()[0]

        # 平均耗时
        cursor = conn.execute(
            "SELECT AVG(duration) FROM request_history WHERE duration IS NOT NULL"
        )
        avg_duration = cursor.fetchone()[0] or 0.0

        # 最近错误
        cursor = conn.execute("""
            SELECT request_id, timestamp, error_message
            FROM request_history
            WHERE success = 0
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        recent_errors = [
            {"request_id": row[0], "timestamp": row[1], "error": row[2]}
            for row in cursor.fetchall()
        ]

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": total_requests - successful_requests,
            "success_rate": successful_requests / total_requests
            if total_requests > 0
            else 1.0,
            "avg_duration": avg_duration,
            "recent_errors": recent_errors,
        }