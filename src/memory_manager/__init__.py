"""统一记忆管理器模块入口

重构版本：将大文件拆分为多个小模块

模块结构:
- _base.py: 单例模式 (~103 行)
- _layers.py: 层级访问 (~131 行)
- _search_l1l3.py: L1-L3 搜索 (~70 行)
- _search_l4l5.py: L4-L5 搜索 (~60 行)
- _operations.py: 操作方法 (~146 行)
"""

from typing import Any

from ._base import MemoryManagerBase, get_memory_root
from ._layers import (
    get_l1_index_content,
    get_l2_skills_list,
    get_l3_knowledge_list,
    get_l4_user_profile_summary,
    get_l5_archive_stats,
    get_memory_hierarchy_summary,
)
from ._operations import (
    archive_from_event_stream,
    archive_session_to_l5,
    cleanup_old_archives,
    get_l5_archive_by_id,
    get_user_preference_with_context,
    observe_preference_direct,
    observe_user_interaction,
    search_l5_archives,
    update_user_model_dialectical,
)
from ._search import search_all_levels


class MemoryManager(MemoryManagerBase):
    """统一记忆管理器 - 五层架构"""

    def __init__(self, llm_gateway: Any = None) -> None:
        self._do_init(llm_gateway)

    def get_l1_index(self) -> str:
        return get_l1_index_content(self._l1_path)

    def get_l2_skills(self) -> list[str]:
        return get_l2_skills_list(self._l2_path)

    def get_l3_knowledge(self) -> list[str]:
        return get_l3_knowledge_list(self._l3_path)

    def get_l4_user_profile(self) -> str:
        return get_l4_user_profile_summary(self._l4_user_modeling)

    def get_l5_stats(self) -> dict[str, Any]:
        return get_l5_archive_stats(self._l5_archive)

    def search_all_levels(
        self, keyword: str, levels: list[str] | None = None, limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        return search_all_levels(
            self._l1_path, self._l2_path, self._l3_path,
            self._l4_user_modeling, self._l5_archive,
            keyword, levels, limit,
        )

    def observe_user(self, interaction: dict[str, Any]) -> list[str]:
        return observe_user_interaction(self._l4_user_modeling, interaction)

    def observe_preference(
        self, key: str, value: str, context: str | None = None, confidence: float = 0.8
    ) -> str:
        return observe_preference_direct(self._l4_user_modeling, key, value, context, confidence)

    async def update_user_model(self) -> dict[str, Any]:
        return await update_user_model_dialectical(self._l4_user_modeling)

    def get_user_preference(self, key: str, context: str | None = None) -> dict[str, Any]:
        return get_user_preference_with_context(self._l4_user_modeling, key, context)

    async def archive_session(
        self, session_id: str, events: list[dict[str, Any]], metadata: dict[str, Any] | None = None
    ) -> str:
        return await archive_session_to_l5(self._l5_archive, session_id, events, metadata)

    async def archive_from_stream(self, event_stream: Any, metadata: dict[str, Any] | None = None) -> str:
        return await archive_from_event_stream(self._l5_archive, event_stream, metadata)

    def search_archives(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        return search_l5_archives(self._l5_archive, keyword, limit)

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        return get_l5_archive_by_id(self._l5_archive, archive_id)

    def get_memory_hierarchy_summary(self) -> str:
        return get_memory_hierarchy_summary(
            self._l1_path, self._l2_path, self._l3_path,
            self._l4_user_modeling, self._l5_archive,
        )

    def cleanup_old_archives(self, max_age_days: int = 90) -> int:
        return cleanup_old_archives(self._l5_archive, max_age_days)


def get_memory_manager(llm_gateway: Any = None) -> MemoryManager:
    """获取 MemoryManager 单例"""
    if MemoryManager._instance is None:
        MemoryManager._instance = MemoryManager(llm_gateway)
    elif llm_gateway and not MemoryManager._instance._llm_gateway:
        MemoryManager._instance.set_llm_gateway(llm_gateway)
    return MemoryManager._instance


__all__ = ["MemoryManager", "get_memory_manager"]