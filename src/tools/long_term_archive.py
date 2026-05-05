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
    # 主类
    LongTermArchiveLayer,
    # 数据库
    ArchiveDBConnection,
    _get_archive_db_path,
    # 归档操作
    archive_session,
    get_archive,
    get_archives_by_session,
    delete_archive,
    store_events,
    # 搜索
    search_with_context,
    search_by_time_range,
    tokenize_for_fts5,
    # 摘要
    generate_summary,
    extract_key_findings,
    simple_summary,
    simple_findings,
    # 清理
    get_archive_stats,
    cleanup_old_archives,
    sync_summary_markers,
    # 注册
    register_archive_tools,
)

# 导出所有公共 API（保持向后兼容）
__all__ = [
    # 主类
    "LongTermArchiveLayer",
    # 数据库
    "ArchiveDBConnection",
    "_get_archive_db_path",
    # 归档操作
    "archive_session",
    "get_archive",
    "get_archives_by_session",
    "delete_archive",
    "store_events",
    # 搜索
    "search_with_context",
    "search_by_time_range",
    "tokenize_for_fts5",
    # 摘要
    "generate_summary",
    "extract_key_findings",
    "simple_summary",
    "simple_findings",
    # 清理
    "get_archive_stats",
    "cleanup_old_archives",
    "sync_summary_markers",
    # 注册
    "register_archive_tools",
]