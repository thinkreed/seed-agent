"""
Skill 执行结果追踪 - SQLite 后端 (wrapper)

调用 session_db.py 的 gene_outcomes 相关函数。

核心功能：
- _record_skill_outcome: 记录 Skill 执行结果
- _get_skill_stats: 获取 Skill 统计
- _list_banned_skills: 列出被禁用的 Skill
- _get_top_skills: 获取高价值 Skill
"""

import logging

logger = logging.getLogger(__name__)


def _record_skill_outcome(
    skill_name: str,
    outcome: str,
    score: float = 1.0,
    signals: list | None = None,
    session_id: str | None = None,
    context: str | None = None,
) -> str:
    """
    Record skill execution outcome to gene_outcomes table.

    Called after skill execution completes:
    - AgentLoop: after tool execution iteration
    - AutonomousExplorer: after autonomous task completion
    - RalphLoop: after cycle completion

    Args:
        skill_name: Skill identifier
        outcome: 'success' | 'failed' | 'partial'
        score: 0.0 - 1.0 (granular success measure)
        signals: Trigger signal patterns (list of strings)
        session_id: Links to session_messages table
        context: Optional execution context summary

    Returns:
        Status message with updated statistics
    """
    try:
        from src.tools.session_db import record_skill_outcome as db_record

        return db_record(skill_name, outcome, score, signals, session_id, context)
    except ImportError:
        return "Error: session_db module not available"
    except Exception as e:
        return f"Error recording outcome: {type(e).__name__}: {str(e)[:100]}"


def _get_skill_stats(skill_name: str) -> str:
    """
    Get aggregated outcome statistics for a skill.

    Returns formatted string with:
    - total attempts, successes, failures
    - success rate, Laplace-smoothed rate
    - recent success rate (last 30 days)
    - is_banned status, selection value
    """
    try:
        from src.tools.session_db import get_skill_stats as db_stats

        stats = db_stats(skill_name)
        if "error" in stats:
            return f"Error: {stats['error']}"

        output = f"Skill Statistics: {skill_name}\n"
        output += f"- Total attempts: {stats['total']}\n"
        output += f"- Successes: {stats['successes']}, Failures: {stats['failures']}\n"
        output += f"- Success rate: {stats['success_rate']:.1%}\n"
        output += f"- Laplace rate: {stats['laplace_rate']:.1%}\n"
        output += f"- Recent rate (30d): {stats['recent_success_rate']:.1%}\n"
        output += f"- Selection value: {stats['selection_value']:.3f}\n"
        output += f"- Banned: {stats['is_banned']}\n"

        if stats["last_success"]:
            output += f"- Last success: {stats['last_success']}\n"
        if stats["last_failure"]:
            output += f"- Last failure: {stats['last_failure']}\n"

        return output
    except ImportError:
        return "Error: session_db module not available"
    except Exception as e:
        return f"Error getting stats: {type(e).__name__}: {str(e)[:100]}"


def _list_banned_skills() -> str:
    """
    List skills with value below ban_threshold.

    Returns formatted list with:
    - skill_name, total_attempts, current_value
    - success_rate, ban_reason, suggested_action
    """
    try:
        from src.tools.session_db import list_banned_skills as db_list

        banned = db_list()
        if not banned:
            return "No banned skills found."

        output = "Banned Skills:\n"
        for s in banned:
            output += f"\n- {s['skill_name']}\n"
            output += f"  Attempts: {s['total_attempts']}, Value: {s['current_value']:.3f}\n"
            output += f"  Success rate: {s['success_rate']:.1%}\n"
            output += f"  Reason: {s['ban_reason']}\n"
            output += f"  Action: {s['suggested_action']}\n"

        return output
    except ImportError:
        return "Error: session_db module not available"
    except Exception as e:
        return f"Error listing banned skills: {type(e).__name__}: {str(e)[:100]}"


def _get_top_skills(limit: int = 10) -> str:
    """
    Get top skills by selection value.

    Args:
        limit: Maximum number to return

    Returns:
        Formatted list of top skills
    """
    try:
        from src.tools.session_db import get_top_skills as db_top

        top = db_top(limit)
        if not top:
            return "No skills with outcome history found."

        output = f"Top {len(top)} Skills (by selection value):\n"
        for s in top:
            output += f"\n- {s['skill_name']}\n"
            output += f"  Value: {s['selection_value']:.3f}, Rate: {s['success_rate']:.1%}\n"
            output += f"  Attempts: {s['total']}\n"

        return output
    except ImportError:
        return "Error: session_db module not available"
    except Exception as e:
        return f"Error getting top skills: {type(e).__name__}: {str(e)[:100]}"