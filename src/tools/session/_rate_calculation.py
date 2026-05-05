"""Skill 分数计算模块

包含 Skill 分数和状态计算功能：
- _calculate_rates
- _compute_selection_value_with_timestamp
"""

import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


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
    from src.tools.session._basic_stats import (
        MEMORY_GRAPH_CONFIG,
        _compute_ban_status,
        _get_skill_recent_stats,
    )

    success_rate = successes / total if total > 0 else 0.0
    laplace_rate = (successes + 1) / (total + 2)

    recent_days: int = MEMORY_GRAPH_CONFIG["recent_days"]
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
    from src.tools.session._basic_stats import MEMORY_GRAPH_CONFIG

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


__all__ = ["_calculate_rates", "_compute_selection_value_with_timestamp"]