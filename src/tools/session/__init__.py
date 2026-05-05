"""
Session 子模块包

导出 SessionDB 类和公共函数。
"""

from src.tools.session._cleanup import (
    cleanup_old_outcomes,
    get_session_stats,
    optimize_index,
    rebuild_index,
)
from src.tools.session._load import (
    _find_session,
    _format_session_message,
    list_sessions,
    load_session_history,
)
from src.tools.session._save import (
    _build_message_batches,
    _insert_fts_index,
    _parse_tool_calls,
    _upsert_session_meta,
    save_session_history,
)
from src.tools.session._schema import (
    create_gene_outcomes_indexes,
    create_gene_outcomes_schema,
    create_gene_outcomes_triggers,
    create_schema,
    create_session_messages_schema,
    create_sessions_meta_schema,
)
from src.tools.session._search import (
    _apply_filters,
    _fallback_search,
    _get_context,
    _highlight_match,
    search_history,
    search_with_filters,
)
from src.tools.session._skill_outcomes import (
    BannedSkillInfo,
    get_skill_stats,
    get_top_skills,
    list_banned_skills,
    record_skill_outcome,
    search_outcomes_by_signal,
)

# 导出所有公共接口
__all__ = [
    # Skill outcomes
    "BannedSkillInfo",
    "_apply_filters",
    "_build_message_batches",
    "_fallback_search",
    "_find_session",
    "_format_session_message",
    "_get_context",
    "_highlight_match",
    "_insert_fts_index",
    "_parse_tool_calls",
    "_upsert_session_meta",
    # Cleanup
    "cleanup_old_outcomes",
    "create_gene_outcomes_indexes",
    "create_gene_outcomes_schema",
    "create_gene_outcomes_triggers",
    # Schema
    "create_schema",
    "create_session_messages_schema",
    "create_sessions_meta_schema",
    "get_session_stats",
    "get_skill_stats",
    "get_top_skills",
    "list_banned_skills",
    "list_sessions",
    # Load
    "load_session_history",
    "optimize_index",
    "rebuild_index",
    "record_skill_outcome",
    # Save
    "save_session_history",
    # Search
    "search_history",
    "search_outcomes_by_signal",
    "search_with_filters",
]
