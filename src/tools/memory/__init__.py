"""记忆工具模块 - L1-L4 + TTRL"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

from ._archive_wrapper import _archive_session_events, _get_archive_details, _get_archive_stats, _get_memory_hierarchy, _search_archives
from ._consolidation_lock import LOCK_STALE_MS, ConsolidationLock, acquire_dream_lock
from ._extract_cursor import CURSOR_STALE_MS, ExtractCursor, get_extract_cursor
from ._memory_search import _build_memory_context_block, read_memory_index, search_memory, start_long_term_update
from ._memory_write import ALLOWED_SOURCES_FOR_L1L2L3, DEDUPLICATION_THRESHOLD, DENIED_SOURCES_FOR_L1L2L3, ValidationResult, VerifiedSource, _check_existing_memory, _compute_similarity, _get_memory_root, _get_path, _get_sessions_dir, _validate_skill_format, _validate_source, write_memory
from ._session_history import _list_sessions, _load_session_history, _save_session_history, _search_history
from ._session_history_jsonl import _generate_session_filename
from ._skill_outcomes import _get_skill_stats, _get_top_skills, _list_banned_skills, _record_skill_outcome
from ._ttrl import ConsolidationResult, ExecutionTrace, JudgementType, MemoryEntry, MemorySource, TTRLProcessor, get_ttrl_processor, ttrl_add_memory, ttrl_add_trace, ttrl_batch_evaluate, ttrl_consolidate, ttrl_get_stats
from ._user_modeling_wrapper import _get_user_preference, _get_user_profile_summary, _list_user_preferences, _observe_user_preference, _update_user_model


def register_memory_tools(registry: "ToolRegistry") -> None:
    """注册记忆工具"""
    # 核心记忆写入
    registry.register("write_memory", write_memory)
    registry.register("read_memory_index", read_memory_index)
    registry.register("search_memory", search_memory)
    registry.register("start_long_term_update", start_long_term_update)
    # 会话历史
    registry.register("save_session_history", _save_session_history)
    registry.register("load_session_history", _load_session_history)
    registry.register("list_sessions", _list_sessions)
    registry.register("search_history", _search_history)
    # Skill 结果追踪
    registry.register("record_skill_outcome", _record_skill_outcome)
    registry.register("get_skill_stats", _get_skill_stats)
    registry.register("list_banned_skills", _list_banned_skills)
    registry.register("get_top_skills", _get_top_skills)
    # L4 用户建模
    registry.register("observe_user_preference", _observe_user_preference)
    registry.register("get_user_preference", _get_user_preference)
    registry.register("get_user_profile_summary", _get_user_profile_summary)
    registry.register("update_user_model", _update_user_model)
    registry.register("list_user_preferences", _list_user_preferences)
    # L5 长期归档
    registry.register("archive_session_events", _archive_session_events)
    registry.register("search_archives", _search_archives)
    registry.register("get_archive_details", _get_archive_details)
    registry.register("get_archive_stats", _get_archive_stats)
    registry.register("get_memory_hierarchy", _get_memory_hierarchy)
    # Wiki P2: TTRL 持续学习
    registry.register("ttrl_add_trace", ttrl_add_trace)
    registry.register("ttrl_batch_evaluate", ttrl_batch_evaluate)
    registry.register("ttrl_add_memory", ttrl_add_memory)
    registry.register("ttrl_consolidate", ttrl_consolidate)
    registry.register("ttrl_get_stats", ttrl_get_stats)
    logger.info("Memory tools registered: 27 tools")


__all__ = ["ALLOWED_SOURCES_FOR_L1L2L3", "CURSOR_STALE_MS", "DEDUPLICATION_THRESHOLD", "DENIED_SOURCES_FOR_L1L2L3", "LOCK_STALE_MS", "ConsolidationLock", "ConsolidationResult", "ExecutionTrace", "ExtractCursor", "JudgementType", "MemoryEntry", "MemorySource", "TTRLProcessor", "ValidationResult", "VerifiedSource", "_archive_session_events", "_build_memory_context_block", "_check_existing_memory", "_compute_similarity", "_get_archive_details", "_get_archive_stats", "_get_memory_hierarchy", "_get_skill_stats", "_get_top_skills", "_get_user_preference", "_get_user_profile_summary", "_list_banned_skills", "_list_sessions", "_list_user_preferences", "_load_session_history", "_observe_user_preference", "_record_skill_outcome", "_save_session_history", "_search_archives", "_search_history", "_update_user_model", "_validate_source", "acquire_dream_lock", "get_extract_cursor", "get_ttrl_processor", "read_memory_index", "register_memory_tools", "search_memory", "start_long_term_update", "ttrl_add_memory", "ttrl_add_trace", "ttrl_batch_evaluate", "ttrl_consolidate", "ttrl_get_stats", "write_memory"]