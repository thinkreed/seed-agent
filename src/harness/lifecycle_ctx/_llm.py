"""
LLM 调用生命周期钩子上下文构建器

提供 LLM 调用前后的钩子上下文构建函数。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.session_event_stream import SessionEventStream


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