"""
Response 生命周期钩子上下文构建器

提供响应处理前后的钩子上下文构建函数。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.session_event_stream import SessionEventStream


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