"""
清理方法模块

包含清理方法：
- cleanup_old_outcomes, optimize_index, rebuild_index, get_session_stats
"""

import logging
import sqlite3

from src.tools.session._skill_outcomes import MEMORY_GRAPH_CONFIG

logger = logging.getLogger(__name__)


def cleanup_old_outcomes(
    conn: sqlite3.Connection, max_entries_per_skill: int | None = None
) -> int:
    """
    清理过旧的执行记录 (FIFO)

    Args:
        conn: 数据库连接
        max_entries_per_skill: 每个 Skill 最大保留记录数

    Returns:
        清理的记录总数
    """
    max_entries = (
        max_entries_per_skill or MEMORY_GRAPH_CONFIG["max_entries_per_skill"]
    )
    total_deleted = 0

    try:
        # 找出超限的 Skill
        rows = conn.execute(
            """
            SELECT skill_name, COUNT(*) as count
            FROM gene_outcomes
            GROUP BY skill_name
            HAVING COUNT(*) > ?
        """,
            (max_entries,),
        ).fetchall()

        for row in rows:
            skill_name = row["skill_name"]
            excess = row["count"] - max_entries

            # 删除最旧的记录
            cursor = conn.execute(
                """
                DELETE FROM gene_outcomes
                WHERE skill_name = ? AND id IN (
                    SELECT id FROM gene_outcomes
                    WHERE skill_name = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (skill_name, skill_name, excess),
            )
            total_deleted += cursor.rowcount

        conn.commit()
        if total_deleted > 0:
            logger.info(
                f"Cleanup completed: deleted {total_deleted} records from {len(rows)} skills"
            )
        return total_deleted
    except sqlite3.OperationalError:
        logger.exception("Database operational error during cleanup")
        return 0
    except sqlite3.IntegrityError:
        logger.exception("Database integrity error during cleanup")
        return 0
    except Exception:
        logger.exception("Unexpected error during cleanup")
        return 0


def optimize_index(conn: sqlite3.Connection) -> str:
    """优化 FTS5 索引"""
    try:
        conn.execute(
            "INSERT INTO session_messages_fts(session_messages_fts) VALUES('optimize')"
        )
        conn.commit()
        return "FTS5 index optimized."
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error optimizing index")
        return f"Error optimizing index (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error optimizing index")
        return f"Error optimizing index: {type(e).__name__}: {e!s}"


def rebuild_index(conn: sqlite3.Connection) -> str:
    """重建 FTS5 索引"""
    try:
        conn.execute(
            "INSERT INTO session_messages_fts(session_messages_fts) VALUES('rebuild')"
        )
        conn.commit()
        return "FTS5 index rebuilt."
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error rebuilding index")
        return f"Error rebuilding index (database issue): {e!s}"
    except Exception as e:
        logger.exception("Unexpected error rebuilding index")
        return f"Error rebuilding index: {type(e).__name__}: {e!s}"


def get_session_stats(conn: sqlite3.Connection, session_id: str) -> dict:
    """获取会话统计信息"""
    try:
        meta = conn.execute(
            "SELECT * FROM sessions_meta WHERE session_id = ?", (session_id,)
        ).fetchone()

        if not meta:
            return {"error": "Session not found", "error_type": "not_found"}

        fts_size = conn.execute(
            """
            SELECT COUNT(*) as fts_count
            FROM session_messages_fts
            WHERE session_id = ?
        """,
            (session_id,),
        ).fetchone()

        return {
            "session_id": meta["session_id"],
            "created_at": meta["created_at"],
            "last_updated": meta["last_updated"],
            "message_count": meta["message_count"],
            "fts_indexed_count": fts_size["fts_count"],
            "has_summary": bool(meta["summary"]),
        }
    except sqlite3.OperationalError as e:
        logger.exception("Database operational error getting session stats")
        return {"error": str(e), "error_type": "database_operational"}
    except Exception as e:
        logger.exception("Unexpected error getting session stats")
        return {"error": str(e), "error_type": type(e).__name__}


__all__ = [
    "cleanup_old_outcomes",
    "get_session_stats",
    "optimize_index",
    "rebuild_index",
]
