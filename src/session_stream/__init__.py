"""
Session 事件流模块

基于 Harness Engineering "宠物与牲畜基础设施哲学" 设计：
- Session 是宠物：精心培育、持久保存、不可丢失
- 核心接口：emitEvent() 记录事件、getEvents() 读取事件
- 只追加的日志，天然支持重放和状态恢复

重构说明：
- 类型定义移至 _types.py
- 持久化逻辑移至 _persist.py
- 重放逻辑移至 _replay.py
- 清理逻辑移至 _cleanup.py
- 摘要逻辑移至 _summary.py
- 上下文构建移至 _context.py
"""

from src.session_stream._types import EventType, MAX_EVENT_AGE_DAYS, MAX_IN_MEMORY_EVENTS
from src.session_stream._persist import EventPersistence, _get_default_storage_path
from src.session_stream._replay import StateReplay
from src.session_stream._cleanup import EventCleanup
from src.session_stream._summary import SummaryManager
from src.session_stream._context import ContextBuilder

__all__ = [
    "EventType",
    "MAX_IN_MEMORY_EVENTS",
    "MAX_EVENT_AGE_DAYS",
    "EventPersistence",
    "StateReplay",
    "EventCleanup",
    "SummaryManager",
    "ContextBuilder",
    "_get_default_storage_path",
]