"""
统一记忆管理器 - 五层架构集成

负责管理 L1-L5 五层记忆系统：
- L1: 索引层 (notes.md) - 快速参考索引
- L2: 技能层 (skills/*.md) - 可复用操作流程
- L3: 知识层 (knowledge/*.md) - 跨任务模式和原则
- L4: 用户建模层 (SQLite) - 黑格尔辩证式用户理解
- L5: 工作日志层 (SQLite+FTS5) - 长期归档和LLM摘要

核心功能:
1. 跨层查询接口
2. 统一写入管理
3. 层级关联维护
4. 自动进化触发
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.tools.long_term_archive import LongTermArchiveLayer
from src.tools.user_modeling import UserModelingLayer

logger = logging.getLogger(__name__)

# 记忆根目录
MEMORY_ROOT = Path(os.path.expanduser("~")) / ".seed" / "memory"


class MemoryManager:
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

    _instance: "MemoryManager | None" = None
    _initialized: bool = False
    _lock: Any = None  # threading.Lock

    def __new__(cls) -> "MemoryManager":
        """单例模式"""
        import threading

        if cls._instance is None:
            if cls._lock is None:
                cls._lock = threading.Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, llm_gateway: Any = None):
        import threading

        if MemoryManager._initialized:
            return

        with MemoryManager._lock or threading.Lock():
            if MemoryManager._initialized:
                return
            MemoryManager._initialized = True

        self._llm_gateway = llm_gateway

        # 初始化各层
        self._l4_user_modeling = UserModelingLayer()
        self._l5_archive = LongTermArchiveLayer()

        # 设置 LLM Gateway
        if llm_gateway:
            self._l4_user_modeling.set_llm_gateway(llm_gateway)
            self._l5_archive.set_llm_gateway(llm_gateway)

        # L1-L3 路径
        self._l1_path = MEMORY_ROOT / "notes.md"
        self._l2_path = MEMORY_ROOT / "skills"
        self._l3_path = MEMORY_ROOT / "knowledge"

        logger.info("MemoryManager initialized with 5 layers")

    def set_llm_gateway(self, gateway: Any) -> None:
        """设置 LLM Gateway"""
        self._llm_gateway = gateway
        self._l4_user_modeling.set_llm_gateway(gateway)
        self._l5_archive.set_llm_gateway(gateway)

    # === 层级访问 ===

    def get_l1_index(self) -> str:
        """获取 L1 索引内容"""
        if self._l1_path.exists():
            return self._l1_path.read_text(encoding="utf-8")
        return "L1 索引不存在"

    def get_l2_skills(self) -> list[str]:
        """获取 L2 技能列表"""
        if self._l2_path.exists():
            skills = []
            for skill_dir in self._l2_path.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append(skill_dir.name)
            return skills
        return []

    def get_l3_knowledge(self) -> list[str]:
        """获取 L3 知识列表"""
        if self._l3_path.exists():
            knowledge = []
            for f in self._l3_path.glob("*.md"):
                knowledge.append(f.stem)
            return knowledge
        return []

    def get_l4_user_profile(self) -> str:
        """获取 L4 用户画像摘要"""
        return self._l4_user_modeling.get_user_profile_summary()

    def get_l5_stats(self) -> dict[str, Any]:
        """获取 L5 归档统计"""
        return self._l5_archive.get_archive_stats()

    # === 跨层查询 ===

    def search_all_levels(
        self,
        keyword: str,
        levels: list[str] | None = None,
        limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        """跨层搜索

        Args:
            keyword: 搜索关键词
            levels: 搜索层级列表 (默认全部)
            limit: 每层结果限制

        Returns:
            {
                "L1": [...],
                "L2": [...],
                "L3": [...],
                "L4": [...],
                "L5": [...]
            }
        """
        if levels is None:
            levels = ["L1", "L2", "L3", "L4", "L5"]

        results: dict[str, list[dict[str, Any]]] = {}

        # L1 搜索
        if "L1" in levels:
            results["L1"] = self._search_l1(keyword)

        # L2 搜索
        if "L2" in levels:
            results["L2"] = self._search_l2(keyword, limit)

        # L3 搜索
        if "L3" in levels:
            results["L3"] = self._search_l3(keyword, limit)

        # L4 用户画像搜索
        if "L4" in levels:
            results["L4"] = self._search_l4(keyword)

        # L5 归档搜索
        if "L5" in levels:
            results["L5"] = self._l5_archive.search_with_context(keyword, limit)

        return results

    def _search_l1(self, keyword: str) -> list[dict[str, Any]]:
        """搜索 L1 索引"""
        if not self._l1_path.exists():
            return []

        content = self._l1_path.read_text(encoding="utf-8")
        keyword_lower = keyword.lower()

        if keyword_lower in content.lower():
            return [{
                "level": "L1",
                "source": "notes.md",
                "matched": True,
                "type": "index_entry"
            }]
        return []

    def _search_l2(self, keyword: str, limit: int) -> list[dict[str, Any]]:
        """搜索 L2 技能"""
        results = []
        if not self._l2_path.exists():
            return results

        keyword_lower = keyword.lower()

        for skill_dir in self._l2_path.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                if keyword_lower in content.lower():
                    results.append({
                        "level": "L2",
                        "source": skill_dir.name,
                        "matched": True,
                        "type": "skill"
                    })
                    if len(results) >= limit:
                        break
            except IOError:
                continue

        return results

    def _search_l3(self, keyword: str, limit: int) -> list[dict[str, Any]]:
        """搜索 L3 知识"""
        results = []
        if not self._l3_path.exists():
            return results

        keyword_lower = keyword.lower()

        for f in self._l3_path.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                if keyword_lower in content.lower():
                    results.append({
                        "level": "L3",
                        "source": f.stem,
                        "matched": True,
                        "type": "knowledge"
                    })
                    if len(results) >= limit:
                        break
            except IOError:
                continue

        return results

    def _search_l4(self, keyword: str) -> list[dict[str, Any]]:
        """搜索 L4 用户画像"""
        preferences = self._l4_user_modeling.get_all_preferences()

        results = []
        keyword_lower = keyword.lower()

        for pref_key, pref_data in preferences.items():
            if keyword_lower in pref_key.lower():
                results.append({
                    "level": "L4",
                    "source": pref_key,
                    "value": pref_data.get("usual"),
                    "type": "user_preference"
                })

            usual = pref_data.get("usual", "")
            if usual and keyword_lower in usual.lower():
                results.append({
                    "level": "L4",
                    "source": pref_key,
                    "value": usual,
                    "type": "user_preference"
                })

        return results

    # === 用户观察 ===

    def observe_user(
        self,
        interaction: dict[str, Any]
    ) -> list[str]:
        """观察用户交互

        Args:
            interaction: {
                "user_message": str,
                "agent_response": str,
                "tool_calls": list,
                "feedback": str | None
            }

        Returns:
            观察记录列表
        """
        return self._l4_user_modeling.observe_from_interaction(interaction)

    def observe_preference(
        self,
        key: str,
        value: str,
        context: str | None = None,
        confidence: float = 0.8
    ) -> str:
        """直接观察偏好

        Args:
            key: 偏好键
            value: 偏好值
            context: 上下文
            confidence: 置信度

        Returns:
            观察记录状态
        """
        return self._l4_user_modeling.observe(
            evidence_type="preference",
            data={"key": key, "value": value},
            context=context,
            confidence=confidence
        )

    async def update_user_model(self) -> dict[str, Any]:
        """触发用户模型辩证式更新

        Returns:
            更新报告
        """
        return await self._l4_user_modeling.dialectical_update()

    def get_user_preference(
        self,
        key: str,
        context: str | None = None
    ) -> dict[str, Any]:
        """获取用户偏好

        Args:
            key: 偏好键
            context: 当前上下文

        Returns:
            基于上下文的偏好值
        """
        return self._l4_user_modeling.get_user_preference(key, context)

    # === 会话归档 ===

    async def archive_session(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None
    ) -> str:
        """归档会话到 L5

        Args:
            session_id: 会话 ID
            events: 事件列表
            metadata: 可选元数据

        Returns:
            archive_id
        """
        return await self._l5_archive.archive_session(session_id, events, metadata)

    async def archive_from_stream(
        self,
        event_stream: Any,
        metadata: dict[str, Any] | None = None
    ) -> str:
        """从事件流归档

        Args:
            event_stream: SessionEventStream 实例
            metadata: 可选元数据

        Returns:
            archive_id
        """
        return await self._l5_archive.archive_from_event_stream(event_stream, metadata)

    def search_archives(
        self,
        keyword: str,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """搜索归档

        Args:
            keyword: 搜索关键词
            limit: 结果限制

        Returns:
            归档列表
        """
        return self._l5_archive.search_with_context(keyword, limit)

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        """获取归档详情"""
        return self._l5_archive.get_archive(archive_id)

    # === 层级关联 ===

    def get_memory_hierarchy_summary(self) -> str:
        """获取记忆层级摘要"""
        lines = ["=== 五层记忆架构摘要 ==="]

        # L1
        l1_exists = self._l1_path.exists()
        l1_size = 0
        if l1_exists:
            l1_size = len(self._l1_path.read_text(encoding="utf-8"))
        lines.append(f"L1 索引: {'存在' if l1_exists else '不存在'}, {l1_size} 字符")

        # L2
        l2_skills = self.get_l2_skills()
        lines.append(f"L2 技能: {len(l2_skills)} 个技能")
        if l2_skills:
            lines.append(f"  - {', '.join(l2_skills[:5])}")

        # L3
        l3_knowledge = self.get_l3_knowledge()
        lines.append(f"L3 知识: {len(l3_knowledge)} 条知识")
        if l3_knowledge:
            lines.append(f"  - {', '.join(l3_knowledge[:5])}")

        # L4
        l4_summary = self._l4_user_modeling.get_user_profile_summary()
        l4_prefs = self._l4_user_modeling.get_all_preferences()
        lines.append(f"L4 用户画像: {len(l4_prefs)} 个偏好")
        if l4_prefs:
            lines.append(f"  {l4_summary[:200]}")

        # L5
        l5_stats = self._l5_archive.get_archive_stats()
        lines.append(f"L5 归档: {l5_stats['total_archives']} 个归档, "
                     f"{l5_stats['total_events']} 个事件")

        return chr(10).join(lines)

    # === 清理 ===

    def cleanup_old_archives(self, max_age_days: int = 90) -> int:
        """清理旧归档"""
        return self._l5_archive.cleanup_old_archives(max_age_days)

    def close(self) -> None:
        """关闭所有资源"""
        self._l4_user_modeling.close()
        self._l5_archive.close()
        MemoryManager._instance = None
        MemoryManager._initialized = False


# 全局获取函数
def get_memory_manager(llm_gateway: Any = None) -> MemoryManager:
    """获取 MemoryManager 单例"""
    if MemoryManager._instance is None:
        MemoryManager._instance = MemoryManager(llm_gateway)
    elif llm_gateway and not MemoryManager._instance._llm_gateway:
        MemoryManager._instance.set_llm_gateway(llm_gateway)
    return MemoryManager._instance