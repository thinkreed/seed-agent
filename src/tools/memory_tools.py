"""
记忆工具模块 - 兼容层

此文件已重构为 src/tools/memory/ 子包。
所有功能从子模块导入，保持向后兼容性。

迁移指南:
- 原 memory_tools.py -> src/tools/memory/__init__.py
- 新导入: from src.tools.memory import write_memory, register_memory_tools
- 或: from src.tools.memory import * (获取所有公共 API)

子模块结构:
- _memory_write.py: L1-L4 记忆写入核心逻辑
- _memory_search.py: 记忆搜索和索引读取
- _session_history.py: 会话历史 SQLite wrapper
- _session_history_jsonl.py: JSONL fallback 实现
- _skill_outcomes.py: Skill 执行结果追踪
- _user_modeling.py: 用户建模 wrapper

版本: v2.0 (拆分重构版 - 向后兼容)
"""

# 从新的子包导入所有功能
from src.tools.memory import (
    # 长期归档
    _archive_session_events,
    _generate_session_filename,
    _get_archive_details,
    _get_archive_stats,
    _get_memory_hierarchy,
    # 核心写入
    _get_memory_root,
    _get_path,
    _get_sessions_dir,
    # Skill 结果追踪
    _get_skill_stats,
    _get_top_skills,
    # 用户建模
    _get_user_preference,
    _get_user_profile_summary,
    _list_banned_skills,
    # 会话历史
    _list_sessions,
    _list_user_preferences,
    _load_session_history,
    _observe_user_preference,
    _record_skill_outcome,
    _save_session_history,
    _search_archives,
    _search_history,
    _update_user_model,
    _validate_skill_format,
    # 搜索和索引
    read_memory_index,
    # 注册函数
    register_memory_tools,
    search_memory,
    start_long_term_update,
    write_memory,
)

# 导出所有公共 API（保持向后兼容）
__all__ = [
    # 核心写入
    "write_memory",
    "_get_path",
    "_validate_skill_format",
    "_get_memory_root",
    "_get_sessions_dir",
    # 搜索和索引
    "read_memory_index",
    "search_memory",
    "start_long_term_update",
    # 会话历史
    "_save_session_history",
    "_load_session_history",
    "_list_sessions",
    "_search_history",
    "_generate_session_filename",
    # Skill 结果追踪
    "_record_skill_outcome",
    "_get_skill_stats",
    "_list_banned_skills",
    "_get_top_skills",
    # 用户建模
    "_observe_user_preference",
    "_get_user_preference",
    "_get_user_profile_summary",
    "_update_user_model",
    "_list_user_preferences",
    # 长期归档
    "_archive_session_events",
    "_search_archives",
    "_get_archive_details",
    "_get_archive_stats",
    "_get_memory_hierarchy",
    # 注册函数
    "register_memory_tools",
]