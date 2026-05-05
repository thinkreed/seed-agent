"""统一记忆管理器模块入口

重构版本：将大文件拆分为多个小模块
此文件保留为向后兼容的导入入口

模块结构:
- _base.py: 单例模式、基础初始化 (~90 行)
- _layers.py: L1-L5 层级访问 (~90 行)
- _search.py: 跨层搜索 (~110 行)
- _operations.py: 用户观察、会话归档 (~90 行)

总计: 4 个模块，每个均 < 150 行
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
    """统一记忆管理器 - 五层架构

    核心功能:
    1. 管理 L1-L5 五层记忆
    2. 提供跨层查询接口
    3. 自动触发 L4 辩证式更新
    4. 自动触发 L5 会话归档
    5. 维护层级关联

    使用方式:
    - 通过 get_memory_manager() 获取单例
    - 调用 search_all_levels() 进行跨层搜索
    - 调用 observe_user() 观察用户行为
    - 调用 archive_session() 归档会话
    """

    def __init__(self, llm_gateway: Any = None) -> None:
        self._do_init(llm_gateway)

    # === 层级访问 ===

    def get_l1_index(self) -> str:
        """获取 L1 索引内容"""
        return get_l1_index_content(self._l1_path)

    def get_l2_skills(self) -> list[str]:
        """获取 L2 技能列表"""
        return get_l2_skills_list(self._l2_path)

    def get_l3_knowledge(self) -> list[str]:
        """获取 L3 知识列表"""
        return get_l3_knowledge_list(self._l3_path)

    def get_l4_user_profile(self) -> str:
        """获取 L4 用户画像摘要"""
        return get_l4_user_profile_summary(self._l4_user_modeling)

    def get_l5_stats(self) -> dict[str, Any]:
        """获取 L5 归档统计"""
        return get_l5_archive_stats(self._l5_archive)

    # === 跨层查询 ===

    def search_all_levels(
        self, keyword: str, levels: list[str] | None = None, limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        """跨层搜索"""
        return search_all_levels(
            self._l1_path,
            self._l2_path,
            self._l3_path,
            self._l4_user_modeling,
            self._l5_archive,
            keyword,
            levels,
            limit,
        )

    # === 用户观察 ===

    def observe_user(self, interaction: dict[str, Any]) -> list[str]:
        """观察用户交互"""
        return observe_user_interaction(self._l4_user_modeling, interaction)

    def observe_preference(
        self, key: str, value: str, context: str | None = None, confidence: float = 0.8
    ) -> str:
        """直接观察偏好"""
        return observe_preference_direct(
            self._l4_user_modeling, key, value, context, confidence
        )

    async def update_user_model(self) -> dict[str, Any]:
        """触发用户模型辩证式更新"""
        return await update_user_model_dialectical(self._l4_user_modeling)

    def get_user_preference(
        self, key: str, context: str | None = None
    ) -> dict[str, Any]:
        """获取用户偏好"""
        return get_user_preference_with_context(self._l4_user_modeling, key, context)

    # === 会话归档 ===

    async def archive_session(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """归档会话到 L5"""
        return await archive_session_to_l5(
            self._l5_archive, session_id, events, metadata
        )

    async def archive_from_stream(
        self, event_stream: Any, metadata: dict[str, Any] | None = None
    ) -> str:
        """从事件流归档"""
        return await archive_from_event_stream(self._l5_archive, event_stream, metadata)

    def search_archives(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """搜索归档"""
        return search_l5_archives(self._l5_archive, keyword, limit)

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        """获取归档详情"""
        return get_l5_archive_by_id(self._l5_archive, archive_id)

    # === 层级关联 ===

    def get_memory_hierarchy_summary(self) -> str:
        """获取记忆层级摘要"""
        return get_memory_hierarchy_summary(
            self._l1_path,
            self._l2_path,
            self._l3_path,
            self._l4_user_modeling,
            self._l5_archive,
        )

    # === 清理 ===

    def cleanup_old_archives(self, max_age_days: int = 90) -> int:
        """清理旧归档"""
        return cleanup_old_archives(self._l5_archive, max_age_days)


def get_memory_manager(llm_gateway: Any = None) -> MemoryManager:
    """获取 MemoryManager 单例"""
    if MemoryManager._instance is None:
        MemoryManager._instance = MemoryManager(llm_gateway)
    elif llm_gateway and not MemoryManager._instance._llm_gateway:
        MemoryManager._instance.set_llm_gateway(llm_gateway)
    return MemoryManager._instance


__all__ = ["MemoryManager", "get_memory_manager"]