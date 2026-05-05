"""
Skill 结果方法模块

包含 Skill 执行结果记录和统计方法：
- record_skill_outcome, _execute_skill_outcome_insert
- _get_skill_basic_stats, _get_skill_recent_stats, _compute_ban_status
- get_skill_stats, _get_default_stats, _calculate_rates
- _compute_selection_value_with_timestamp
- list_banned_skills, get_top_skills, search_outcomes_by_signal
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import TypedDict

from src.tools.fts_utils import sanitize_fts_query

logger = logging.getLogger(__name__)

# 配置常量（从主模块导入或使用默认值）
try:
    from src.shared_config import get_memory_graph_config

    _config = get_memory_graph_config()
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": _config.half_life_days,
        "ban_threshold": _config.ban_threshold,
        "min_attempts_for_ban": _config.min_attempts_for_ban,
        "memory_weight": _config.memory_weight,
        "trigger_weight": _config.trigger_weight,
        "cold_start_penalty": _config.cold_start_penalty,
        "recent_boost_factor": _config.recent_boost_factor,
        "recent_days": _config.recent_days,
        "max_entries_per_skill": _config.max_entries_per_skill,
    }
except ImportError:
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": 30,
        "ban_threshold": 0.18,
        "min_attempts_for_ban": 2,
        "memory_weight": 0.6,
        "trigger_weight": 0.4,
        "cold_start_penalty": 0.5,
        "recent_boost_factor": 0.2,
        "recent_days": 30,
        "max_entries_per_skill": 5000,
    }


class BannedSkillInfo(TypedDict):
    """禁用 Skill 信息类型定义"""

    skill_name: str
    total_attempts: int
    current_value: float
    success_rate: float
    laplace_rate: float
    last_time: str
    ban_reason: str
    suggested_action: str


def record_skill_outcome(
    conn: sqlite3.Connection,
    skill_name: str,
    outcome: str,
    score: float = 1.0,
    signals: list[str] | None = None,
    session_id: str | None = None,
    context: str | None = None,
    intent: str | None = None,
    blast_radius: dict | None = None,
) -> str:
    """记录 Skill 执行结果到 gene_outcomes 表"""
    if outcome not in ("success", "failed", "partial"):
        return f"Invalid outcome status: {outcome}"
    if not (0.0 <= score <= 1.0):
        return f"Invalid score: {score} (must be 0.0-1.0)"

    signal_pattern = " ".join(signals) if signals else ""
    timestamp = datetime.now(UTC).isoformat()
    blast_radius_json = json.dumps(blast_radius) if blast_radius else None

    try:
        _execute_skill_outcome_insert(
            conn,
            skill_name,
            signal_pattern,
            outcome,
            score,
            session_id,
            timestamp,
            context,
            intent,
            blast_radius_json,
        )
        stats = get_skill_stats(conn, skill_name)
        return (
            f"Outcome recorded: {skill_name} -> {outcome} "
            f"(score: {score}). Stats: {stats['total']} total, "
            f"{stats['success_rate']:.1%} success"
        )
    except sqlite3.IntegrityError:
        return f"Duplicate outcome ignored: {skill_name} at {timestamp}"
    except Exception as e:
        return f"Error recording outcome: {e!s}"


def _execute_skill_outcome_insert(
    conn: sqlite3.Connection,
    skill_name: str,
    signal_pattern: str,
    outcome: str,
    score: float,
    session_id: str | None,
    timestamp: str,
    context: str | None,
    intent: str | None,
    blast_radius_json: str | None,
) -> None:
    """执行 Skill 结果插入"""
    conn.execute(
        """
        INSERT INTO gene_outcomes
            (skill_name, signal_pattern, outcome_status, outcome_score,
             session_id, timestamp, iteration_context, intent, blast_radius)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            skill_name,
            signal_pattern,
            outcome,
            score,
            session_id,
            timestamp,
            context,
            intent,
            blast_radius_json,
        ),
    )
    conn.commit()


def _get_skill_basic_stats(conn: sqlite3.Connection, skill_name: str) -> dict:
    """获取 Skill 基础统计信息"""
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN outcome_status = 'failed' THEN 1 ELSE 0 END) as failures,
            MAX(CASE WHEN outcome_status = 'success' THEN timestamp ELSE NULL END) as last_success,
            MAX(CASE WHEN outcome_status = 'failed' THEN timestamp ELSE NULL END) as last_failure,
            AVG(outcome_score) as avg_score
        FROM gene_outcomes
        WHERE skill_name = ?
    """,
        (skill_name,),
    ).fetchone()
    return dict(row) if row else {}


def _get_skill_recent_stats(
    conn: sqlite3.Connection, skill_name: str, recent_days: int = 30
) -> dict:
    """获取 Skill 近期统计信息 (最近 N 天)"""
    recent_row = conn.execute(
        """
        SELECT
            COUNT(*) as recent_total,
            SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as recent_successes
        FROM gene_outcomes
        WHERE skill_name = ? AND timestamp > datetime('now', ?)
    """,
        (skill_name, f"-{recent_days} days"),
    ).fetchone()
    return dict(recent_row) if recent_row else {}


def _compute_ban_status(skill_name: str, total: int, selection_value: float) -> bool:
    """检查 Skill 是否应被禁用"""
    min_attempts = MEMORY_GRAPH_CONFIG["min_attempts_for_ban"]
    ban_threshold = MEMORY_GRAPH_CONFIG["ban_threshold"]
    return total >= min_attempts and selection_value < ban_threshold


def get_skill_stats(conn: sqlite3.Connection, skill_name: str) -> dict:
    """获取 Skill 的聚合统计信息"""
    try:
        row = _get_skill_basic_stats(conn, skill_name)
        if not row or row.get("total", 0) == 0:
            return _get_default_stats()

        total = row["total"]
        successes = row["successes"]

        # 传递 basic_stats 避免 N+1 查询
        rates = _calculate_rates(conn, skill_name, successes, total, basic_stats=row)
        return {
            "total": total,
            "successes": successes,
            "failures": row["failures"],
            "success_rate": rates["success_rate"],
            "laplace_rate": rates["laplace_rate"],
            "recent_success_rate": rates["recent_success_rate"],
            "last_success": row["last_success"],
            "last_failure": row["last_failure"],
            "avg_score": row["avg_score"],
            "is_banned": rates["is_banned"],
            "selection_value": rates["selection_value"],
        }
    except Exception as e:
        return {"error": str(e)}


def _get_default_stats() -> dict:
    """返回冷启动默认统计"""
    return {
        "total": 0,
        "successes": 0,
        "failures": 0,
        "success_rate": 0.0,
        "recent_success_rate": 0.0,
        "last_success": None,
        "last_failure": None,
        "is_banned": False,
        "selection_value": 0.0,
        "laplace_rate": 0.5,
    }


def _calculate_rates(
    conn: sqlite3.Connection,
    skill_name: str,
    successes: int,
    total: int,
    basic_stats: dict | None = None,
) -> dict:
    """计算各种分数和状态

    Args:
        conn: 数据库连接
        skill_name: Skill 名称
        successes: 成功次数
        total: 总次数
        basic_stats: 基础统计信息（可选，用于避免重复查询）
    """
    success_rate = successes / total if total > 0 else 0.0
    laplace_rate = (successes + 1) / (total + 2)

    recent_days: int = MEMORY_GRAPH_CONFIG["recent_days"]  # type: ignore[assignment]
    recent_row = _get_skill_recent_stats(conn, skill_name, recent_days)
    recent_success_rate = 0.0
    if recent_row and recent_row.get("recent_total", 0) > 0:
        recent_success_rate = recent_row["recent_successes"] / recent_row["recent_total"]

    # 使用传入的 basic_stats 避免 N+1 查询
    last_timestamp = basic_stats.get("last_success") if basic_stats else None
    selection_value = _compute_selection_value_with_timestamp(
        successes, total, recent_success_rate, last_timestamp
    )
    is_banned = _compute_ban_status(skill_name, total, selection_value)

    return {
        "success_rate": success_rate,
        "laplace_rate": laplace_rate,
        "recent_success_rate": recent_success_rate,
        "selection_value": selection_value,
        "is_banned": is_banned,
    }


def _compute_selection_value_with_timestamp(
    successes: int,
    total: int,
    recent_success_rate: float,
    last_timestamp: str | None = None,
) -> float:
    """
    计算选择分数 (GEP-style) - 使用传入的时间戳避免重复查询

    公式: value = laplace_rate * decay_weight + recent_boost
    """
    half_life = MEMORY_GRAPH_CONFIG["half_life_days"]
    recent_boost_factor = MEMORY_GRAPH_CONFIG["recent_boost_factor"]

    # Laplace 平滑概率
    p = (successes + 1) / (total + 2)

    # 计算衰减权重（使用传入的时间戳）
    decay_weight = 1.0
    if last_timestamp:
        try:
            last_time = datetime.fromisoformat(last_timestamp)
            age_days = (datetime.now(UTC) - last_time).days
            decay_weight = 0.5 ** (age_days / half_life)
        except Exception as e:
            logger.debug(f"Decay calculation failed: {type(e).__name__}")
            decay_weight = 1.0

    # 近期成功加成
    recent_boost = recent_success_rate * recent_boost_factor

    return p * decay_weight + recent_boost


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


__all__ = [
    "MEMORY_GRAPH_CONFIG",
    "BannedSkillInfo",
    "_calculate_rates",
    "_compute_ban_status",
    "_compute_selection_value_with_timestamp",
    "_execute_skill_outcome_insert",
    "_get_default_stats",
    "_get_skill_basic_stats",
    "_get_skill_recent_stats",
    "get_skill_stats",
    "get_top_skills",
    "list_banned_skills",
    "record_skill_outcome",
    "search_outcomes_by_signal",
]
