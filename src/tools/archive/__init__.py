"""L5 工作日志层 - FTS5 + LLM 自动摘要"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

from ._archive_operations import archive_session, delete_archive, get_archive, get_archives_by_session, store_events
from ._cleanup import cleanup_old_archives, get_archive_stats, sync_summary_markers
from ._db_schema import ArchiveDBConnection, _get_archive_db_path
from ._fts_search import search_by_time_range, search_with_context, tokenize_for_fts5
from ._llm_summary import extract_key_findings, generate_summary, simple_findings, simple_summary

if TYPE_CHECKING:
    from src.client import LLMGateway

logger = logging.getLogger(__name__)


class LongTermArchiveLayer:
    """L5 工作日志 - FTS5 + LLM 摘要"""

    _instance: "LongTermArchiveLayer | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> Self:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None: cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __init__(self, db_path: str | Path | None = None, llm_gateway: "LLMGateway | None" = None):
        with LongTermArchiveLayer._lock:
            if LongTermArchiveLayer._initialized: return
            LongTermArchiveLayer._initialized = True
        self._db = ArchiveDBConnection(db_path)
        self._llm_gateway = llm_gateway

    def set_llm_gateway(self, gateway: "LLMGateway") -> None: self._llm_gateway = gateway
    def close(self) -> None: self._db.close()

    # === 归档 ===
    async def archive_session(self, session_id: str, events: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> str:
        if not events: return "Error: No events to archive"
        summary = await generate_summary(events, self._llm_gateway)
        key_findings = await extract_key_findings(events, self._llm_gateway)
        return await archive_session(self._db, session_id, events, summary, key_findings, metadata)

    async def archive_from_event_stream(self, event_stream: Any, metadata: dict[str, Any] | None = None) -> str:
        events = event_stream.get_events()
        return await self.archive_session(event_stream.session_id, events, metadata)

    # === 搜索 ===
    def search_with_context(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]: return search_with_context(self._db, keyword, limit)
    def search_by_time_range(self, start_time: str, end_time: str, limit: int = 50) -> list[dict[str, Any]]: return search_by_time_range(self._db, start_time, end_time, limit)

    # === 检索 ===
    def get_archive(self, archive_id: str) -> dict[str, Any] | None: return get_archive(self._db, archive_id)
    def get_archives_by_session(self, session_id: str) -> list[dict[str, Any]]: return get_archives_by_session(self._db, session_id)

    # === 统计 ===
    def get_archive_stats(self) -> dict[str, Any]: return get_archive_stats(self._db)

    # === 清理 ===
    def delete_archive(self, archive_id: str) -> str: return delete_archive(self._db, archive_id)
    def cleanup_old_archives(self, max_age_days: int = 90, keep_count: int = 100) -> int: return cleanup_old_archives(self._db, max_age_days, keep_count)
    def sync_summary_markers(self, event_stream: Any) -> str: return sync_summary_markers(self._db, event_stream)


def register_archive_tools(registry: Any) -> None:
    """注册归档工具到 Registry"""
    archive = LongTermArchiveLayer()

    def _archive_session_wrapper(session_id: str, events_json: str, metadata_json: str | None = None) -> str:
        import json
        try:
            events = json.loads(events_json) if events_json else []
            if not events: return "Error: No events to archive"
            return "提示: 请使用 LongTermArchiveLayer.archive_session() 在异步环境中调用"
        except json.JSONDecodeError as e: return f"Error parsing JSON: {type(e).__name__}"

    def _search_archives_wrapper(keyword: str, limit: int = 20) -> str:
        results = archive.search_with_context(keyword, limit)
        if not results: return f"未找到匹配 '{keyword}' 的归档"
        output = f"找到 {len(results)} 个匹配 '{keyword}' 的归档:\n"
        for r in results: output += f"\n[{r['archive_id']}]\n- 会话: {r['session_id']}\n- 摘要: {r['summary'][:100]}...\n"
        return output

    def _get_archive_details_wrapper(archive_id: str) -> str:
        details = archive.get_archive(archive_id)
        if not details: return f"归档不存在: {archive_id}"
        return f"归档详情: {archive_id}\n- 会话 ID: {details['session_id']}\n- 创建时间: {details['created_at']}\n- 事件数: {details['events_count']}\n- 摘要: {details['summary']}\n"

    def _get_archive_stats_wrapper() -> str:
        stats = archive.get_archive_stats()
        return f"L5 归档统计:\n- 总归档数: {stats['total_archives']}\n- 总事件数: {stats['total_events']}\n- 平均事件数/归档: {stats['avg_events_per_archive']}\n"

    registry.register("archive_session_events", _archive_session_wrapper)
    registry.register("search_archives", _search_archives_wrapper)
    registry.register("get_archive_details", _get_archive_details_wrapper)
    registry.register("get_archive_stats", _get_archive_stats_wrapper)
    logger.info("Archive tools registered: 4 tools")


__all__ = ["ArchiveDBConnection", "LongTermArchiveLayer", "_get_archive_db_path", "archive_session", "cleanup_old_archives", "delete_archive", "extract_key_findings", "generate_summary", "get_archive", "get_archive_stats", "get_archives_by_session", "register_archive_tools", "search_by_time_range", "search_with_context", "simple_findings", "simple_summary", "store_events", "sync_summary_markers", "tokenize_for_fts5"]