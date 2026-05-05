"""Skill 统计计算模块

包含 Skill 统计计算相关功能：
- _get_skill_basic_stats, _get_skill_recent_stats
- _compute_ban_status
- get_skill_stats, _get_default_stats
- _calculate_rates
- _compute_selection_value_with_timestamp
"""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TypedDict

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


__all__ = [
    "MEMORY_GRAPH_CONFIG",
    "BannedSkillInfo",
    "_get_skill_basic_stats",
    "_get_skill_recent_stats",
    "_compute_ban_status",
    "get_skill_stats",
    "_get_default_stats",
    "_calculate_rates",
    "_compute_selection_value_with_timestamp",
]