"""
记忆工具模块

负责:
1. 四级记忆写入 (L1 索引、L2 技能、L3 知识、L4 原始数据)
2. 会话历史管理 (SQLite + FTS5 后端，JSONL fallback)
3. 技能执行结果记录 (gene_outcomes 表、成功率追踪)
4. 用户建模 (黑格尔辩证式进化)
5. L5 长期归档 (FTS5 + LLM 摘要)

模块结构:
- _memory_write.py: L1-L4 记忆写入核心逻辑
- _memory_search.py: 记忆搜索和索引读取
- _session_history.py: 会话历史 SQLite wrapper
- _session_history_jsonl.py: JSONL fallback 实现
- _skill_outcomes.py: Skill 执行结果追踪
- _user_modeling.py: 用户建模 wrapper
- _archive_wrapper.py: L5 归档 wrapper

版本: v2.0 (拆分重构版)
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

# 导入子模块功能
from ._memory_write import (
    _get_memory_root,
    _get_path,
    _get_sessions_dir,
    _validate_skill_format,
    write_memory,
)
from ._memory_search import (
    read_memory_index,
    search_memory,
    start_long_term_update,
)
from ._session_history import (
    _list_sessions,
    _load_session_history,
    _save_session_history,
    _search_history,
)
from ._session_history_jsonl import _generate_session_filename
from ._skill_outcomes import (
    _get_skill_stats,
    _get_top_skills,
    _list_banned_skills,
    _record_skill_outcome,
)


# ==================== L4 用户建模工具 wrapper ====================


def _observe_user_preference(
    key: str, value: str, context: str | None = None, confidence: float = 0.8
) -> str:
    """观察用户偏好证据"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.observe(
            evidence_type="preference",
            data={"key": key, "value": value},
            context=context,
            confidence=confidence,
        )
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error observing preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_preference(key: str, context: str | None = None) -> str:
    """获取用户偏好（基于上下文）"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        result = user_model.get_user_preference(key, context)

        output = f"用户偏好 '{key}':\n"
        output += f"- 值: {result['value']}\n"
        output += f"- 原因: {result['reason']}\n"
        output += f"- 置信度: {result['confidence']:.2f}\n"
        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error getting preference: {type(e).__name__}: {str(e)[:100]}"


def _get_user_profile_summary() -> str:
    """获取用户画像完整摘要"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        return user_model.get_user_profile_summary()
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error getting profile: {type(e).__name__}: {str(e)[:100]}"


def _update_user_model() -> str:
    """触发用户模型辩证式更新"""
    return (
        "提示: 用户模型辩证式更新需要异步执行。\n"
        "请使用 MemoryManager.update_user_model() 在异步环境中调用。\n"
        "流程: 检测矛盾 -> 内部推理 -> 升级模型 (不覆盖)"
    )


def _list_user_preferences() -> str:
    """列出所有用户偏好"""
    try:
        from src.tools.user_modeling import UserModelingLayer

        user_model = UserModelingLayer()
        preferences = user_model.get_all_preferences()

        if not preferences:
            return "无用户偏好记录"

        output = "用户偏好列表:\n"
        for key, pref_data in preferences.items():
            usual = pref_data.get("usual", "未知")
            exceptions = pref_data.get("exceptions", {})
            confidence = pref_data.get("confidence", 0.0)
            output += f"\n- {key}: {usual} (置信度 {confidence:.2f})\n"
            if exceptions:
                for exc_key, exc_val in exceptions.items():
                    if exc_key != "previously":
                        output += f"  例外 [{exc_key}]: {exc_val.get('value', '未知')}\n"
        return output
    except ImportError:
        return "Error: user_modeling module not available"
    except Exception as e:
        return f"Error listing preferences: {type(e).__name__}: {str(e)[:100]}"


# ==================== L5 长期归档工具 wrapper ====================


def _archive_session_events(
    session_id: str, events_json: str, metadata_json: str | None = None
) -> str:
    """归档会话事件到长期存储"""
    import json

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
        return f"Error searching archives: {type(e).__name__}: {str(e)[:100]}"


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
        return f"Error getting archive: {type(e).__name__}: {str(e)[:100]}"


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
        return f"Error getting stats: {type(e).__name__}: {str(e)[:100]}"


def _get_memory_hierarchy() -> str:
    """获取五层记忆架构摘要"""
    try:
        from src.memory_manager import get_memory_manager

        manager = get_memory_manager()
        return manager.get_memory_hierarchy_summary()
    except ImportError:
        return "Error: memory_manager module not available"
    except Exception as e:
        return f"Error getting hierarchy: {type(e).__name__}: {str(e)[:100]}"


# ==================== 工具注册 ====================


def register_memory_tools(registry: "ToolRegistry") -> None:
    """Register memory tools to the Agent system.

    注册以下工具:
    - write_memory: 标准化记忆写入
    - read_memory_index: 读取 L1 索引
    - search_memory: 跨层级搜索
    - start_long_term_update: 经验提炼触发

    会话历史工具 (SQLite + FTS5):
    - save_session_history: 保存会话
    - load_session_history: 加载会话
    - list_sessions: 列出会话
    - search_history: 搜索历史

    Skill 执行结果追踪:
    - record_skill_outcome: 记录执行结果
    - get_skill_stats: 获取统计
    - list_banned_skills: 列出禁用
    - get_top_skills: 获取高价值

    L4 用户建模:
    - observe_user_preference: 观察偏好
    - get_user_preference: 获取偏好
    - get_user_profile_summary: 获取画像
    - update_user_model: 更新模型
    - list_user_preferences: 列出偏好

    L5 长期归档:
    - archive_session_events: 归档事件
    - search_archives: 搜索归档
    - get_archive_details: 获取详情
    - get_archive_stats: 获取统计
    - get_memory_hierarchy: 获取层级摘要
    """
    # 核心记忆写入
    registry.register("write_memory", write_memory)
    registry.register("read_memory_index", read_memory_index)
    registry.register("search_memory", search_memory)
    registry.register("start_long_term_update", start_long_term_update)

    # 会话历史工具 - SQLite + FTS5 后端
    registry.register("save_session_history", _save_session_history)
    registry.register("load_session_history", _load_session_history)
    registry.register("list_sessions", _list_sessions)
    registry.register("search_history", _search_history)

    # Memory Graph 工具 - Skill 执行结果追踪
    registry.register("record_skill_outcome", _record_skill_outcome)
    registry.register("get_skill_stats", _get_skill_stats)
    registry.register("list_banned_skills", _list_banned_skills)
    registry.register("get_top_skills", _get_top_skills)

    # L4 用户建模工具 - 黑格尔辩证式进化
    registry.register("observe_user_preference", _observe_user_preference)
    registry.register("get_user_preference", _get_user_preference)
    registry.register("get_user_profile_summary", _get_user_profile_summary)
    registry.register("update_user_model", _update_user_model)
    registry.register("list_user_preferences", _list_user_preferences)

    # L5 工作日志工具 - 长期归档 + LLM摘要
    registry.register("archive_session_events", _archive_session_events)
    registry.register("search_archives", _search_archives)
    registry.register("get_archive_details", _get_archive_details)
    registry.register("get_archive_stats", _get_archive_stats)
    registry.register("get_memory_hierarchy", _get_memory_hierarchy)

    logger.info("Memory tools registered: 22 tools")


# 导出公共 API
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