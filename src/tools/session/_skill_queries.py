"""Skill 查询模块

包含 Skill 批量查询功能：
- list_banned_skills
- get_top_skills
- search_outcomes_by_signal
"""

import logging
import sqlite3

from src.tools.fts_utils import sanitize_fts_query
from src.tools.session._stats_calculation import (
    BannedSkillInfo,
    MEMORY_GRAPH_CONFIG,
)

logger = logging.getLogger(__name__)


def list_banned_skills(conn: sqlite3.Connection) -> list[BannedSkillInfo]:
    """
    列出被禁用的 Skill（低于 ban_threshold）（批量查询优化，避免 N+1）

    Returns:
        [
            {
                'skill_name': 'xxx',
                'total_attempts': N,
                'current_value': 0.XX,
                'success_rate': 0.XX,
                'ban_reason': 'Low success rate',
                'suggested_action': 'Review strategy or retire'
            }
        ]
    """
    min_attempts = MEMORY_GRAPH_CONFIG["min_attempts_for_ban"]
    ban_threshold = MEMORY_GRAPH_CONFIG["ban_threshold"]

    try:
        # 单次批量查询：计算所有 skill 的统计数据
        rows = conn.execute(
            """
            SELECT
                skill_name,
                COUNT(*) as total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
                MAX(timestamp) as last_time,
                AVG(outcome_score) as avg_score
            FROM gene_outcomes
            GROUP BY skill_name
            HAVING COUNT(*) >= ?
        """,
            (min_attempts,),
        ).fetchall()

        banned: list[BannedSkillInfo] = []
        for row in rows:
            skill_name = row["skill_name"]
            total = row["total"]
            successes = row["successes"]

            # 计算统计数据（避免调用 get_skill_stats）
            success_rate = successes / total if total > 0 else 0.0
            laplace_rate = (successes + 1) / (total + 2)
            selection_value = laplace_rate

            if selection_value < ban_threshold:
                banned.append(
                    {
                        "skill_name": skill_name,
                        "total_attempts": total,
                        "current_value": selection_value,
                        "success_rate": success_rate,
                        "laplace_rate": laplace_rate,
                        "last_time": row["last_time"],
                        "ban_reason": "Low success rate",
                        "suggested_action": "Review strategy or retire",
                    }
                )

        return banned
    except Exception as e:
        logger.warning(f"Failed to list banned skills: {type(e).__name__}: {e}")
        return []


def get_top_skills(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """
    获取成功率最高的 Skill（批量查询优化，避免 N+1）

    Returns:
        按 selection_value 排序的 Skill 列表
    """
    try:
        # 单次批量查询：计算所有 skill 的统计数据
        rows = conn.execute("""
            SELECT
                skill_name,
                COUNT(*) as total,
                SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes
            FROM gene_outcomes
            GROUP BY skill_name
            HAVING COUNT(*) > 0
        """).fetchall()

        skill_values = []
        for row in rows:
            skill_name = row["skill_name"]
            total = row["total"]
            successes = row["successes"]

            # 计算统计数据（避免调用 get_skill_stats）
            success_rate = successes / total if total > 0 else 0.0
            laplace_rate = (successes + 1) / (total + 2)
            selection_value = laplace_rate

            skill_values.append(
                {
                    "skill_name": skill_name,
                    "selection_value": selection_value,
                    "success_rate": success_rate,
                    "total": total,
                }
            )

        # 按选择分数排序
        skill_values.sort(key=lambda x: x["selection_value"], reverse=True)
        return skill_values[:limit]
    except Exception as e:
        logger.warning(f"Failed to get top skills: {type(e).__name__}: {e}")
        return []


def search_outcomes_by_signal(
    conn: sqlite3.Connection, signal: str, limit: int = 20
) -> list[dict]:
    """
    根据信号模式搜索历史执行结果

    Args:
        conn: 数据库连接
        signal: 搜索信号
        limit: 结果限制

    Returns:
        匹配的执行记录列表
    """
    try:
        fts_query = sanitize_fts_query(signal)
        if not fts_query:
            return []

        rows = conn.execute(
            """
            SELECT
                g.id, g.skill_name, g.signal_pattern, g.outcome_status, g.outcome_score, g.timestamp
            FROM gene_outcomes g
            JOIN gene_outcomes_fts fts ON g.id = fts.rowid
            WHERE gene_outcomes_fts MATCH ?
            ORDER BY g.timestamp DESC
            LIMIT ?
        """,
            (fts_query, limit),
        ).fetchall()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"Failed to get context messages: {type(e).__name__}: {e}")
        return []


__all__ = ["list_banned_skills", "get_top_skills", "search_outcomes_by_signal"]