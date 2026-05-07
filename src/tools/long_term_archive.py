"""
L5 工作日志层 - 兼容层

此文件已重构为 src/tools/archive/ 子包。
所有功能从子模块导入，保持向后兼容性。

迁移指南:
- 原 long_term_archive.py -> src/tools/archive/__init__.py
- 新导入: from src.tools.archive import LongTermArchiveLayer
- 或: from src.tools.archive import * (获取所有公共 API)

子模块结构:
- _db_schema.py: 数据库 Schema 和连接管理
- _archive_operations.py: 归档操作（存储、检索）
- _fts_search.py: FTS5 搜索实现
- _llm_summary.py: LLM 摘要生成
- _cleanup.py: 清理和统计

版本: v2.0 (拆分重构版 - 向后兼容)
"""

# 从新的子包导入所有功能
from src.tools.archive import (
    # 数据库
    ArchiveDBConnection,
    # 主类
    LongTermArchiveLayer,
    _get_archive_db_path,
    # 归档操作
    archive_session,
    cleanup_old_archives,
    delete_archive,
    extract_key_findings,
    # 摘要
    generate_summary,
    get_archive,
    # 清理
    get_archive_stats,
    get_archives_by_session,
    # 注册
    register_archive_tools,
    search_by_time_range,
    # 搜索
    search_with_context,
    simple_findings,
    simple_summary,
    store_events,
    sync_summary_markers,
    tokenize_for_fts5,
)

# 导出所有公共 API（保持向后兼容）
__all__ = [
    # 数据库
    "ArchiveDBConnection",
    # 主类
    "LongTermArchiveLayer",
    "_get_archive_db_path",
    # 归档操作
    "archive_session",
    "cleanup_old_archives",
    "delete_archive",
    "extract_key_findings",
    # 摘要
    "generate_summary",
    "get_archive",
    # 清理
    "get_archive_stats",
    "get_archives_by_session",
    # 注册
    "register_archive_tools",
    "search_by_time_range",
    # 搜索
    "search_with_context",
    "simple_findings",
    "simple_summary",
    "store_events",
    "sync_summary_markers",
    "tokenize_for_fts5",
]