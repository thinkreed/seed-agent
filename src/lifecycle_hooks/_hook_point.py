"""钩子节点枚举和描述

定义智能体生命周期的所有关键节点。
"""

from enum import StrEnum


class HookPoint(StrEnum):
    """钩子节点枚举

    定义智能体生命周期的所有关键节点
    """

    # 会话生命周期
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_PAUSE = "session_pause"
    SESSION_RESUME = "session_resume"

    # 工具执行生命周期
    TOOL_CALL_BEFORE = "tool_call_before"
    TOOL_CALL_AFTER = "tool_call_after"
    TOOL_CALL_ERROR = "tool_call_error"

    # LLM 调用生命周期
    LLM_CALL_BEFORE = "llm_call_before"
    LLM_CALL_AFTER = "llm_call_after"
    LLM_STREAM_START = "llm_stream_start"
    LLM_STREAM_CHUNK = "llm_stream_chunk"
    LLM_STREAM_END = "llm_stream_end"

    # 响应生命周期
    RESPONSE_BEFORE = "response_before"
    RESPONSE_AFTER = "response_after"

    # 上下文生命周期
    CONTEXT_RESET_BEFORE = "context_reset_before"
    CONTEXT_RESET_AFTER = "context_reset_after"
    SUMMARY_GENERATED = "summary_generated"

    # 子代理生命周期
    SUBAGENT_SPAWN = "subagent_spawn"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    SUBAGENT_ERROR = "subagent_error"

    # Ralph Loop 生命周期
    RALPH_ITERATION_START = "ralph_iteration_start"
    RALPH_ITERATION_END = "ralph_iteration_end"
    RALPH_COMPLETION_CHECK = "ralph_completion_check"
    RALPH_CONTEXT_RESET = "ralph_context_reset"

    # Ask User 生命周期
    USER_QUESTION = "user_question"
    USER_WAITING = "user_waiting"
    USER_RESPONSE = "user_response"
    USER_CANCELLED = "user_cancelled"

    # 执行控制生命周期
    EXECUTION_CANCEL = "execution_cancel"
    EXECUTION_PAUSE = "execution_pause"
    EXECUTION_RESUME = "execution_resume"

    # 后台任务生命周期
    TASK_START = "task_start"
    TASK_END = "task_end"
    TASK_CANCEL = "task_cancel"
    TASK_ERROR = "task_error"
    GRACE_PERIOD_START = "grace_period_start"
    GRACE_PERIOD_END = "grace_period_end"

    # 关闭生命周期
    SHUTDOWN_START = "shutdown_start"
    SHUTDOWN_COMPLETE = "shutdown_complete"


# 钩子节点描述（常量字典）
HOOK_POINT_DESCRIPTIONS: dict[str, str] = {
    HookPoint.SESSION_START.value: "会话开始",
    HookPoint.SESSION_END.value: "会话结束",
    HookPoint.SESSION_PAUSE.value: "会话暂停",
    HookPoint.SESSION_RESUME.value: "会话恢复",
    HookPoint.TOOL_CALL_BEFORE.value: "工具调用前",
    HookPoint.TOOL_CALL_AFTER.value: "工具调用后",
    HookPoint.TOOL_CALL_ERROR.value: "工具调用错误",
    HookPoint.LLM_CALL_BEFORE.value: "LLM 调用前",
    HookPoint.LLM_CALL_AFTER.value: "LLM 调用后",
    HookPoint.LLM_STREAM_START.value: "LLM 流式响应开始",
    HookPoint.LLM_STREAM_CHUNK.value: "LLM 流式响应块",
    HookPoint.LLM_STREAM_END.value: "LLM 流式响应结束",
    HookPoint.RESPONSE_BEFORE.value: "响应生成前",
    HookPoint.RESPONSE_AFTER.value: "响应生成后",
    HookPoint.CONTEXT_RESET_BEFORE.value: "上下文重置前",
    HookPoint.CONTEXT_RESET_AFTER.value: "上下文重置后",
    HookPoint.SUMMARY_GENERATED.value: "摘要生成后",
    HookPoint.SUBAGENT_SPAWN.value: "子代理创建",
    HookPoint.SUBAGENT_START.value: "子代理开始执行",
    HookPoint.SUBAGENT_END.value: "子代理执行结束",
    HookPoint.SUBAGENT_ERROR.value: "子代理执行错误",
    HookPoint.RALPH_ITERATION_START.value: "Ralph 迭代开始",
    HookPoint.RALPH_ITERATION_END.value: "Ralph 迭代结束",
    HookPoint.RALPH_COMPLETION_CHECK.value: "Ralph 完成检查",
    HookPoint.RALPH_CONTEXT_RESET.value: "Ralph 上下文重置",
    HookPoint.USER_QUESTION.value: "发起用户问题",
    HookPoint.USER_WAITING.value: "等待用户响应",
    HookPoint.USER_RESPONSE.value: "用户响应接收",
    HookPoint.USER_CANCELLED.value: "用户取消",
    HookPoint.EXECUTION_CANCEL.value: "执行被取消",
    HookPoint.EXECUTION_PAUSE.value: "执行暂停",
    HookPoint.EXECUTION_RESUME.value: "执行恢复",
    HookPoint.TASK_START.value: "后台任务开始",
    HookPoint.TASK_END.value: "后台任务结束",
    HookPoint.TASK_CANCEL.value: "后台任务取消",
    HookPoint.TASK_ERROR.value: "后台任务错误",
    HookPoint.GRACE_PERIOD_START.value: "优雅期开始",
    HookPoint.GRACE_PERIOD_END.value: "优雅期结束",
    HookPoint.SHUTDOWN_START.value: "关闭开始",
    HookPoint.SHUTDOWN_COMPLETE.value: "关闭完成",
}


__all__ = ["HOOK_POINT_DESCRIPTIONS", "HookPoint"]