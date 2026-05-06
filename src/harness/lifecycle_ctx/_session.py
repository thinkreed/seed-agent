"""
Session 生命周期钩子上下文构建器

提供会话启动和结束时的钩子上下文构建函数。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.session_event_stream import SessionEventStream


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