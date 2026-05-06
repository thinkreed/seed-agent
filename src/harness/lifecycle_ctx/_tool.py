"""
Tool 调用生命周期钩子上下文构建器

提供工具调用前、后、错误的钩子上下文构建函数。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.session_event_stream import SessionEventStream


def build_tool_call_before_ctx(
    session: "SessionEventStream",
    harness: Any,
    sandbox: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_call_id: str,
) -> dict[str, Any]:
    """构建 tool_call_before 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        sandbox: Sandbox 实例
        tool_name: 工具名称
        tool_args: 工具参数
        tool_call_id: 工具调用 ID

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "sandbox": sandbox,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_call_id": tool_call_id,
    }


def build_tool_call_after_ctx(
    session: "SessionEventStream",
    harness: Any,
    sandbox: Any,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_call_id: str,
    result: str,
    duration_ms: float,
    success: bool,
) -> dict[str, Any]:
    """构建 tool_call_after 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        sandbox: Sandbox 实例
        tool_name: 工具名称
        tool_args: 工具参数
        tool_call_id: 工具调用 ID
        result: 工具执行结果
        duration_ms: 执行时长（毫秒）
        success: 是否成功

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "sandbox": sandbox,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_call_id": tool_call_id,
        "result": result,
        "duration_ms": duration_ms,
        "success": success,
    }


def build_tool_call_error_ctx(
    session: "SessionEventStream",
    harness: Any,
    sandbox: Any,
    tool_name: str,
    tool_call_id: str,
    tool_args: dict[str, Any],
    error: str,
    duration_ms: float | None = None,
) -> dict[str, Any]:
    """构建 tool_call_error 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        sandbox: Sandbox 实例
        tool_name: 工具名称
        tool_call_id: 工具调用 ID
        tool_args: 工具参数
        error: 错误信息
        duration_ms: 执行时长（可选）

    Returns:
        钩子上下文字典
    """
    ctx: dict[str, Any] = {
        "session": session,
        "harness": harness,
        "sandbox": sandbox,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "tool_args": tool_args,
        "error": error[:500],
    }
    if duration_ms is not None:
        ctx["duration_ms"] = duration_ms
    return ctx