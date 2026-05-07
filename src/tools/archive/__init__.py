"""
L5 工作日志层 - FTS5 + LLM 自动摘要

基于 Hermes Agent Session Database 设计：
- SQLite + WAL 模式实现高并发
- FTS5 全文索引 + jieba 中文分词
- LLM 自动生成核心结论摘要

核心功能:
1. 归档会话事件流到长期存储
2. LLM 自动生成核心结论摘要（写读书笔记）
3. FTS5 全文检索 + jieba 中文分词
4. 跨会话知识检索

模块结构:
- _db_schema.py: 数据库 Schema 和连接管理
- _archive_operations.py: 归档操作（存储、检索）
- _fts_search.py: FTS5 搜索实现
- _llm_summary.py: LLM 摘要生成
- _cleanup.py: 清理和统计

版本: v2.0 (拆分重构版)
"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

from ._archive_operations import (
    archive_session,
    delete_archive,
    get_archive,
    get_archives_by_session,
    store_events,
)
from ._cleanup import cleanup_old_archives, get_archive_stats, sync_summary_markers
from ._db_schema import ArchiveDBConnection, _get_archive_db_path
from ._fts_search import search_by_time_range, search_with_context, tokenize_for_fts5
from ._llm_summary import (
    extract_key_findings,
    generate_summary,
    simple_findings,
    simple_summary,
)

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class LongTermArchiveLayer:
    """L5 工作日志 - FTS5 + LLM 摘要

    核心功能:
    1. archive_session(): 归档会话事件流
    2. search_with_context(): 语义搜索 + 摘要提取
    3. get_archive(): 获取完整归档
    4. get_archive_stats(): 归档统计
    """

    _instance: "LongTermArchiveLayer | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> Self:
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(
        self, db_path: str | Path | None = None, llm_gateway: "LLMGateway | None" = None
    ):
        with LongTermArchiveLayer._lock:
            if LongTermArchiveLayer._initialized:
                return
            LongTermArchiveLayer._initialized = True

        self._db = ArchiveDBConnection(db_path)
        self._llm_gateway = llm_gateway

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway（用于自动摘要）"""
        self._llm_gateway = gateway

    def close(self) -> None:
        """关闭数据库连接"""
        self._db.close()

    # === 归档 ===

    async def archive_session(
        self,
        session_id: str,
        events: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """归档会话

        流程:
        1. LLM 生成核心结论摘要
        2. 存储到数据库
        3. FTS5 自动索引

        Args:
            session_id: 会话 ID
            events: 事件列表
            metadata: 可选元数据

        Returns:
            archive_id
        """
        if not events:
            return "Error: No events to archive"

        # 1. LLM 生成摘要
        summary = await generate_summary(events, self._llm_gateway)
        key_findings = await extract_key_findings(events, self._llm_gateway)

        # 2. 存储归档
        return await archive_session(
            self._db, session_id, events, summary, key_findings, metadata
        )

    async def archive_from_event_stream(
        self, event_stream: Any, metadata: dict[str, Any] | None = None
    ) -> str:
        """从 SessionEventStream 归档

        Args:
            event_stream: SessionEventStream 实例
            metadata: 可选元数据

        Returns:
            archive_id
        """
        events = event_stream.get_events()
        return await self.archive_session(event_stream.session_id, events, metadata)

    # === 搜索 ===

    def search_with_context(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """语义搜索 + 摘要提取"""
        return search_with_context(self._db, keyword, limit)

    def search_by_time_range(
        self, start_time: str, end_time: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """时间范围搜索"""
        return search_by_time_range(self._db, start_time, end_time, limit)

    # === 检索 ===

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        """获取完整归档"""
        return get_archive(self._db, archive_id)

    def get_archives_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话的所有归档"""
        return get_archives_by_session(self._db, session_id)

    # === 统计 ===

    def get_archive_stats(self) -> dict[str, Any]:
        """获取归档统计"""
        return get_archive_stats(self._db)

    # === 清理 ===

    def delete_archive(self, archive_id: str) -> str:
        """删除归档"""
        return delete_archive(self._db, archive_id)

    def cleanup_old_archives(
        self, max_age_days: int = 90, keep_count: int = 100
    ) -> int:
        """清理旧归档"""
        return cleanup_old_archives(self._db, max_age_days, keep_count)

    # === 摘要标记同步 ===

    def sync_summary_markers(self, event_stream: Any) -> str:
        """从事件流同步摘要标记"""
        return sync_summary_markers(self._db, event_stream)


# === 工具注册 ===


def register_archive_tools(registry: Any) -> None:
    """注册归档工具到 Registry

    注册以下工具:
    - archive_session: 归档会话
    - search_archives: 搜索归档
    - get_archive_details: 获取详情
    - get_archive_stats: 获取统计
    """
    # 创建单例实例
    archive = LongTermArchiveLayer()

    # 定义 wrapper 函数
    def _archive_session_wrapper(session_id: str, events_json: str, metadata_json: str | None = None) -> str:
        """归档会话 wrapper"""
        import json
        try:
            events = json.loads(events_json) if events_json else []
            if not events:
                return "Error: No events to archive"
            return "提示: 请使用 LongTermArchiveLayer.archive_session() 在异步环境中调用"
        except json.JSONDecodeError as e:
            return f"Error parsing JSON: {type(e).__name__}"

    def _search_archives_wrapper(keyword: str, limit: int = 20) -> str:
        """搜索归档 wrapper"""
        results = archive.search_with_context(keyword, limit)
        if not results:
            return f"未找到匹配 '{keyword}' 的归档"

        output = f"找到 {len(results)} 个匹配 '{keyword}' 的归档:\n"
        for r in results:
            output += f"\n[{r['archive_id']}]\n"
            output += f"- 会话: {r['session_id']}\n"
            output += f"- 摘要: {r['summary'][:100]}...\n"
        return output

    def _get_archive_details_wrapper(archive_id: str) -> str:
        """获取详情 wrapper"""
        details = archive.get_archive(archive_id)
        if not details:
            return f"归档不存在: {archive_id}"

        output = f"归档详情: {archive_id}\n"
        output += f"- 会话 ID: {details['session_id']}\n"
        output += f"- 创建时间: {details['created_at']}\n"
        output += f"- 事件数: {details['events_count']}\n"
        output += f"- 摘要: {details['summary']}\n"
        return output

    def _get_archive_stats_wrapper() -> str:
        """获取统计 wrapper"""
        stats = archive.get_archive_stats()
        output = "L5 归档统计:\n"
        output += f"- 总归档数: {stats['total_archives']}\n"
        output += f"- 总事件数: {stats['total_events']}\n"
        output += f"- 平均事件数/归档: {stats['avg_events_per_archive']}\n"
        return output

    registry.register("archive_session_events", _archive_session_wrapper)
    registry.register("search_archives", _search_archives_wrapper)
    registry.register("get_archive_details", _get_archive_details_wrapper)
    registry.register("get_archive_stats", _get_archive_stats_wrapper)

    logger.info("Archive tools registered: 4 tools")


# 导出公共 API
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