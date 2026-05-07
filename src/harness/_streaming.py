"""
Harness 流式处理模块

流式对话处理入口点。

内容:
- stream_conversation - 流式执行对话
- stream_resume_with_user_response - 流式恢复执行
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority
from src.session_event_stream import EventType
from src.tools.builtin_tools import clear_ask_user_state

from ._lifecycle_hooks import build_session_start_ctx, trigger_hook
from ._streaming_loop import run_iteration_loop
from ._streaming_utils import process_tool_delta

# Re-export for backward compatibility
__all__ = ["process_tool_delta", "stream_conversation", "stream_resume_with_user_response"]

if TYPE_CHECKING:
    from src.abort_signal import AbortSignal
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream
    from src.tools.ask_user_types import AskUserResult

    from ._metrics import ToolExecutionMetrics


async def stream_conversation(
    initial_prompt: str,
    llm_client: LLMClient,
    session: SessionEventStream,
    sandbox: Sandbox,
    hook_registry: LifecycleHookRegistry | None,
    metrics_deque: deque[ToolExecutionMetrics],
    max_iterations: int,
    context_window: int,
    context_engineering: Any,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    autonomous_mode: bool,
    ask_user_skip_response: str,
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """流式执行对话（支持取消信号、Ask User、生命周期钩子）"""
    harness_ref = None

    # 触发 session_start 钩子
    await trigger_hook(hook_registry, HookPoint.SESSION_START,
        build_session_start_ctx(session, harness_ref, initial_prompt))
    session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

    # 运行迭代循环
    async for chunk in run_iteration_loop(
        llm_client, session, sandbox, harness_ref, hook_registry, metrics_deque,
        max_iterations, context_window, context_engineering, current_task, system_prompt,
        enable_pruning, autonomous_mode, ask_user_skip_response, priority, signal):
        yield chunk


async def stream_resume_with_user_response(
    response: AskUserResult,
    llm_client: LLMClient,
    session: SessionEventStream,
    sandbox: Sandbox,
    hook_registry: LifecycleHookRegistry | None,
    metrics_deque: deque[ToolExecutionMetrics],
    max_iterations: int,
    context_window: int,
    context_engineering: Any,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    pending_tool_call_id: str | None,
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """流式恢复执行（用户响应后）"""
    harness_ref = None

    # 清理等待状态
    clear_ask_user_state()
    session.emit_event(EventType.USER_RESPONSE,
        {"request_id": response.request_id, "responses": [r.to_dict() for r in response.responses],
         "cancelled": response.cancelled, "timeout": response.timeout})

    # 触发 SESSION_RESUME 钩子
    await trigger_hook(hook_registry, HookPoint.SESSION_RESUME,
        {"reason": "user_input_received", "response": response.to_dict()})

    # 构造工具结果
    tool_result = "[USER_CANCELLED]" if response.cancelled else \
                  "[USER_TIMEOUT]" if response.timeout else \
                  f"User selected: {response.get_selected_values()}"
    if pending_tool_call_id:
        session.emit_event(EventType.TOOL_RESULT,
            {"tool_call_id": pending_tool_call_id, "content": tool_result})

    # 运行迭代循环（无自主模式）
    async for chunk in run_iteration_loop(
        llm_client, session, sandbox, harness_ref, hook_registry, metrics_deque,
        max_iterations, context_window, context_engineering, current_task, system_prompt,
        enable_pruning, False, "", priority, signal):
        yield chunk