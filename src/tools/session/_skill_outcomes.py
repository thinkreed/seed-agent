"""
Skill 结果方法模块

包含 Skill 执行结果记录和统计方法：
- record_skill_outcome, _execute_skill_outcome_insert
- _get_skill_basic_stats, _get_skill_recent_stats, _compute_ban_status
- get_skill_stats, _get_default_stats, _calculate_rates
- _compute_selection_value_with_timestamp
- list_banned_skills, get_top_skills, search_outcomes_by_signal

此模块作为 facade，从子模块导入所有功能以保持向后兼容。
"""

# 从子模块导入所有功能
from src.tools.session._outcome_recording import (
    _execute_skill_outcome_insert,
    record_skill_outcome,
)
from src.tools.session._skill_queries import (
    get_top_skills,
    list_banned_skills,
    search_outcomes_by_signal,
)
from src.tools.session._stats_calculation import (
    MEMORY_GRAPH_CONFIG,
    BannedSkillInfo,
    _calculate_rates,
    _compute_ban_status,
    _compute_selection_value_with_timestamp,
    _get_default_stats,
    _get_skill_basic_stats,
    _get_skill_recent_stats,
    get_skill_stats,
)

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