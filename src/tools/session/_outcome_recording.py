"""Skill 结果记录模块

包含 Skill 执行结果记录功能：
- record_skill_outcome
- _execute_skill_outcome_insert
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


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
    from src.tools.session._stats_calculation import get_skill_stats

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


__all__ = ["_execute_skill_outcome_insert", "record_skill_outcome"]