"""
SessionDB 模块级便捷函数

提供模块级单例管理和便捷函数，方便外部调用。

使用方式:
    from src.tools.session_db import save_session_history, search_history
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.session import BannedSkillInfo

# 延迟导入避免循环依赖
_db_instance: "SessionDB | None" = None
_db_lock = threading.Lock()


def _get_db() -> "SessionDB":
    """获取 SessionDB 单例实例"""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                from src.tools.session._session_db_class import SessionDB
                _db_instance = SessionDB()
    # 检查连接是否已关闭，如果关闭则重新创建
    if _db_instance.conn is None:
        with _db_lock:
            _db_instance = SessionDB()
    return _db_instance


def save_session_history(messages: list, summary: str | None = None,
                         session_id: str | None = None) -> str:
    """保存会话历史（模块级便捷函数）"""
    return _get_db().save_session_history(messages, summary, session_id)


def load_session_history(session_id: str) -> str:
    """加载会话历史（模块级便捷函数）"""
    return _get_db().load_session_history(session_id)


def list_sessions(limit: int = 10) -> str:
    """列出会话（模块级便捷函数）"""
    return _get_db().list_sessions(limit)


def search_history(keyword: str, limit: int = 20) -> str:
    """搜索历史（模块级便捷函数）"""
    return _get_db().search_history(keyword, limit)


def record_skill_outcome(skill_name: str, outcome: str, score: float = 1.0,
                         signals: list[str] | None = None, session_id: str | None = None,
                         context: str | None = None) -> str:
    """记录 Skill 执行结果（模块级便捷函数）"""
    return _get_db().record_skill_outcome(skill_name, outcome, score, signals, session_id, context)


def get_skill_stats(skill_name: str) -> dict:
    """获取 Skill 统计信息（模块级便捷函数）"""
    return _get_db().get_skill_stats(skill_name)


def list_banned_skills() -> "list[BannedSkillInfo]":
    """列出被禁用的 Skill（模块级便捷函数）"""
    return _get_db().list_banned_skills()


def get_top_skills(limit: int = 10) -> list[dict]:
    """获取 Top Skills（模块级便捷函数）"""
    return _get_db().get_top_skills(limit)


def search_outcomes_by_signal(signal: str, limit: int = 20) -> list[dict]:
    """按信号搜索执行结果（模块级便捷函数）"""
    return _get_db().search_outcomes_by_signal(signal, limit)


__all__ = [
    "_get_db",
    "get_skill_stats",
    "get_top_skills",
    "list_banned_skills",
    "list_sessions",
    "load_session_history",
    "record_skill_outcome",
    "save_session_history",
    "search_history",
    "search_outcomes_by_signal",
]