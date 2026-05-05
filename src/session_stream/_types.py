"""
Session 事件流类型定义

包含所有事件类型枚举和常量配置。
"""

from enum import StrEnum


# 事件清理配置
MAX_IN_MEMORY_EVENTS = 10000  # 内存中最大事件数
MAX_EVENT_AGE_DAYS = 30  # 事件最大保留天数


class EventType(StrEnum):
    """事件类型枚举"""

    # 对话事件
    USER_INPUT = "user_input"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    # 上下文事件
    SUMMARY_GENERATED = "summary_generated"
    SUMMARY_MARKER = "summary_marker"
    CONTEXT_RESET = "context_reset"

    # 子代理事件
    SUBAGENT_SPAWN = "subagent_spawn"
    SUBAGENT_RESULT = "subagent_result"

    # 系统事件
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    ERROR_OCCURRED = "error_occurred"
    STATE_PERSISTED = "state_persisted"
    SYSTEM_MESSAGE = "system_message"

    # 用户交互事件
    USER_QUESTION = "user_question"
    USER_WAITING = "user_waiting"
    USER_RESPONSE = "user_response"
    USER_CANCELLED = "user_cancelled"

    # 执行控制事件
    EXECUTION_CANCEL = "execution_cancel"
    EXECUTION_PAUSE = "execution_pause"
    EXECUTION_RESUME = "execution_resume"

    # 后台任务事件
    TASK_START = "task_start"
    TASK_END = "task_end"
    TASK_CANCEL = "task_cancel"