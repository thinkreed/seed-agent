"""
生命周期钩子类型定义

包含所有数据类型和枚举定义，与注册逻辑解耦。

Wiki 知识落地 (基于 Qwen-Code Hook 输出类设计):
- DefaultHookOutput: 默认 Hook 输出
- PreToolUseHookOutput: 工具调用前专用输出（支持拒绝/修改）
- PostToolUseHookOutput: 工具调用后专用输出（支持结果修改）
"""

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# === Wiki 知识落地: Hook 专用输出类 ===


@dataclass
class DefaultHookOutput:
    """默认 Hook 输出 (Wiki 知识落地)

    所有 Hook 的基础输出类型。
    """

    success: bool = True
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreToolUseHookOutput(DefaultHookOutput):
    """工具调用前 Hook 输出 (Wiki 知识落地)

    支持拒绝工具调用、修改参数：
    - should_execute: 是否继续执行工具
    - modified_args: 修改后的参数（可选）
    - deny_reason: 拒绝原因（如果 should_execute=False）

    用途：
    - 安全检查 Hook 可拒绝危险工具调用
    - 参数校验 Hook 可修改参数
    """

    should_execute: bool = True
    modified_args: dict[str, Any] | None = None
    deny_reason: str | None = None


@dataclass
class PostToolUseHookOutput(DefaultHookOutput):
    """工具调用后 Hook 输出 (Wiki 知识落地)

    支持修改工具结果：
    - modified_result: 修改后的结果（可选）
    - should_continue: 是否继续执行后续 Hook

    用途：
    - 结果格式化 Hook 可修改输出
    - 日志记录 Hook 可记录结果
    """

    modified_result: Any | None = None
    should_continue: bool = True


@dataclass
class LLMStreamHookOutput(DefaultHookOutput):
    """LLM 流式响应 Hook 输出 (Wiki 知识落地)

    支持修改流式内容：
    - content_chunk: 内容片段（可修改）
    - should_emit: 是否发送到客户端

    用途：
    - 内容过滤 Hook 可修改敏感内容
    - 格式化 Hook 可调整输出格式
    """

    content_chunk: str = ""
    should_emit: bool = True


@dataclass
class UserResponseHookOutput(DefaultHookOutput):
    """用户响应 Hook 输出 (Wiki 知识落地)

    支持修改用户输入：
    - modified_response: 修改后的响应（可选）
    - should_process: 是否处理响应

    用途：
    - 输入验证 Hook 可校验用户输入
    - 预处理 Hook 可标准化输入
    """

    modified_response: str | None = None
    should_process: bool = True


# === 钩子节点枚举 ===


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


@dataclass
class HookExecutionResult:
    """单个钩子执行结果"""

    hook_id: str
    status: str  # "success" | "failed" | "skipped"
    duration_ms: float
    result: Any | None = None
    error: str | None = None


@dataclass
class HookTriggerReport:
    """钩子触发报告"""

    hook_point: str
    hooks_count: int
    hooks_executed: int
    hooks_failed: int
    hooks_skipped: int
    results: list[HookExecutionResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_point": self.hook_point,
            "hooks_count": self.hooks_count,
            "hooks_executed": self.hooks_executed,
            "hooks_failed": self.hooks_failed,
            "hooks_skipped": self.hooks_skipped,
            "total_duration_ms": self.total_duration_ms,
            "results": [
                {
                    "hook_id": r.hook_id,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


@dataclass
class HookStats:
    """钩子执行统计"""

    hook_id: str
    hook_point: str
    priority: int
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    skipped_calls: int = 0
    total_duration_ms: float = 0.0
    last_call_time: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_id": self.hook_id,
            "hook_point": self.hook_point,
            "priority": self.priority,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "skipped_calls": self.skipped_calls,
            "success_rate": self.success_calls / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "avg_duration_ms": self.total_duration_ms / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "last_call_time": self.last_call_time,
            "last_error": self.last_error,
        }


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


# === MessageBus 相关类型 ===


@dataclass
class PendingRequest:
    """等待中的请求 (用于 MessageBus)

    Attributes:
        correlation_id: 请求关联 ID
        request_type: 请求类型
        future: asyncio.Future 用于等待响应
        created_at: 创建时间
        timeout_ms: 超时时间（毫秒）
    """

    correlation_id: str
    request_type: str
    future: asyncio.Future
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    timeout_ms: int = 60000


# 导出列表（供外部导入）
__all__ = [
    # Hook 输出类
    "DefaultHookOutput",
    "PreToolUseHookOutput",
    "PostToolUseHookOutput",
    "LLMStreamHookOutput",
    "UserResponseHookOutput",
    # 钩子节点
    "HookPoint",
    # 钩子结果
    "HookExecutionResult",
    "HookTriggerReport",
    "HookStats",
    # MessageBus 类型
    "PendingRequest",
    # 常量
    "HOOK_POINT_DESCRIPTIONS",
]