"""
Harness 生命周期钩子模块

提取钩子触发函数和上下文构建辅助函数。

内容:
- trigger_hook - 触发生命周期钩子
- build_session_end_ctx - 构建 session_end 钩子上下文
"""

from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint, HookTriggerReport, LifecycleHookRegistry

if TYPE_CHECKING:
    from src.session_event_stream import SessionEventStream


async def trigger_hook(
    hook_registry: LifecycleHookRegistry | None,
    hook_point: HookPoint,
    context: dict[str, Any],
) -> HookTriggerReport | None:
    """触发生命周期钩子

    Args:
        hook_registry: 钩子注册中心（可为 None）
        hook_point: 钩子节点
        context: 钩子上下文

    Returns:
        钩子执行报告（如果没有注册钩子则返回 None）
    """
    if not hook_registry:
        return None

    return await hook_registry.trigger(hook_point, context)


def build_session_end_ctx(
    session: "SessionEventStream",
    harness: Any,
    reason: str,
    error: str | None = None,
    final_response: str | None = None,
) -> dict[str, Any]:
    """构建 session_end 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        reason: 结束原因 ("completed" | "error" | "cancelled" | "max_iterations_exceeded")
        error: 错误信息（仅 error 状态）
        final_response: 最终响应（仅 completed 状态）

    Returns:
        钩子上下文字典
    """
    ctx: dict[str, Any] = {
        "session": session,
        "harness": harness,
        "session_id": session.session_id,
        "reason": reason,
        "event_count": session.get_event_count(),
    }
    if error is not None:
        ctx["error"] = error[:500]  # 限制长度
    if final_response is not None:
        ctx["final_response"] = final_response
    return ctx


def build_session_start_ctx(
    session: "SessionEventStream",
    harness: Any,
    initial_prompt: str,
) -> dict[str, Any]:
    """构建 session_start 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        initial_prompt: 初始输入

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "session_id": session.session_id,
        "initial_prompt": initial_prompt,
    }


def build_llm_call_before_ctx(
    session: "SessionEventStream",
    harness: Any,
    messages: list[dict[str, Any]],
    model_id: str,
    context_window: int,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建 llm_call_before 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        messages: LLM 消息列表
        model_id: 模型 ID
        context_window: 上下文窗口大小
        tools: 工具 schemas

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "messages": messages,
        "model_id": model_id,
        "context_window": context_window,
        "tools": tools,
    }


def build_llm_call_after_ctx(
    session: "SessionEventStream",
    harness: Any,
    response: dict[str, Any],
    duration_ms: float,
) -> dict[str, Any]:
    """构建 llm_call_after 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        response: LLM 响应
        duration_ms: 执行时长（毫秒）

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "response": response,
        "duration_ms": duration_ms,
    }


def build_response_before_ctx(
    session: "SessionEventStream",
    harness: Any,
    iteration: int,
    max_iterations: int,
) -> dict[str, Any]:
    """构建 response_before 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        iteration: 当前迭代次数
        max_iterations: 最大迭代次数

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "iteration": iteration,
        "max_iterations": max_iterations,
    }


def build_response_after_ctx(
    session: "SessionEventStream",
    harness: Any,
    response: dict[str, Any],
    should_continue: bool,
) -> dict[str, Any]:
    """构建 response_after 钩子上下文

    Args:
        session: SessionEventStream 实例
        harness: Harness 实例
        response: LLM 响应
        should_continue: 是否继续循环

    Returns:
        钩子上下文字典
    """
    return {
        "session": session,
        "harness": harness,
        "response": response,
        "should_continue": should_continue,
    }


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