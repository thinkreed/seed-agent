"""
归档操作 - 存储和检索

公共 API 模块，从子模块导入实现，保持向后兼容。
"""

from ._archive_write import archive_session, store_events
from ._archive_read import delete_archive, get_archive, get_archives_by_session
from ._archive_fts import build_event_content_for_fts

__all__ = [
    "archive_session",
    "store_events",
    "get_archive",
    "get_archives_by_session",
    "delete_archive",
    "build_event_content_for_fts",
]