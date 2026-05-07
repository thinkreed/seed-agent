"""
L5 长期归档 Wrapper 模块

提供 L5 长期归档工具 wrapper：
- _archive_session_events: 归档会话事件
- _search_archives: 搜索归档内容
- _get_archive_details: 获取归档详情
- _get_archive_stats: 获取归档统计
- _get_memory_hierarchy: 获取五层记忆架构摘要

核心特性：
- FTS5 全文检索
- LLM 摘要集成
"""

import json
import logging

logger = logging.getLogger(__name__)


def _archive_session_events(
    session_id: str, events_json: str, metadata_json: str | None = None
) -> str:
    """归档会话事件到长期存储"""
    try:
        events = json.loads(events_json) if events_json else []
        if not events:
            return "Error: No events to archive"
        return (
            f"提示: 会话归档需要异步执行。\n"
            f"请使用 MemoryManager.archive_session() 在异步环境中调用。\n"
            f"会话 ID: {session_id}, 事件数: {len(events)}"
        )
    except json.JSONDecodeError as e:
        return f"Error parsing JSON: {type(e).__name__}: {str(e)[:100]}"


def _search_archives(keyword: str, limit: int = 20) -> str:
    """搜索归档内容 (FTS5 全文检索)"""
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        results = archive.search_with_context(keyword, limit)

        if not results:
            return f"未找到匹配 '{keyword}' 的归档"

        output = f"找到 {len(results)} 个匹配 '{keyword}' 的归档:\n"
        for r in results:
            output += f"\n[{r['archive_id']}]\n"
            output += f"- 会话: {r['session_id']}\n"
            output += f"- 摘要: {r['summary'][:100]}...\n"
            output += f"- 匹配片段: {r['matched_snippet'][:50]}...\n"
            if r["key_findings"]:
                output += f"- 关键发现: {r['key_findings'][0]}\n"
            output += f"- 时间: {r['timestamp']}\n"
        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _get_archive_details(archive_id: str) -> str:
    """获取归档详情"""
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        details = archive.get_archive(archive_id)

        if not details:
            return f"归档不存在: {archive_id}"

        output = f"归档详情: {archive_id}\n"
        output += f"- 会话 ID: {details['session_id']}\n"
        output += f"- 创建时间: {details['created_at']}\n"
        output += f"- 事件数: {details['events_count']}\n"
        output += f"- 摘要: {details['summary']}\n"
        if details["key_findings"]:
            output += "- 关键发现:\n"
            for finding in details["key_findings"]:
                output += f"  * {finding}\n"
        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _get_archive_stats() -> str:
    """获取归档统计信息"""
    try:
        from src.tools.long_term_archive import LongTermArchiveLayer

        archive = LongTermArchiveLayer()
        stats = archive.get_archive_stats()

        output = "L5 归档统计:\n"
        output += f"- 总归档数: {stats['total_archives']}\n"
        output += f"- 总事件数: {stats['total_events']}\n"
        output += f"- 平均事件数/归档: {stats['avg_events_per_archive']}\n"
        if stats["recent_archives"]:
            output += "- 最近归档:\n"
            for a in stats["recent_archives"]:
                output += f"  [{a['archive_id']}] {a['events_count']} 事件, {a['created_at']}\n"
        return output
    except ImportError:
        return "Error: long_term_archive module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


def _get_memory_hierarchy() -> str:
    """获取五层记忆架构摘要"""
    try:
        from src.memory_manager import get_memory_manager

        manager = get_memory_manager()
        return manager.get_memory_hierarchy_summary()
    except ImportError:
        return "Error: memory_manager module not available"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)[:100]}"


__all__ = [
    "_archive_session_events",
    "_get_archive_details",
    "_get_archive_stats",
    "_get_memory_hierarchy",
    "_search_archives",
]