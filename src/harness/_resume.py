"""Harness 恢复执行模块

拆分架构:
- _resume_iteration.py: 单轮迭代逻辑
- _resume_utils.py: 辅助函数
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority

from ._lifecycle_hooks import build_session_end_ctx, trigger_hook
from ._metrics import ToolExecutionMetrics
from ._resume_iteration import run_single_iteration
from ._resume_utils import check_and_handle_cancel, handle_user_response

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)


async def resume_with_user_response(
    response: "AskUserResult",
    llm_client: "LLMClient",
    session: "SessionEventStream",
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
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
) -> dict[str, Any]:
    """恢复执行（用户响应后）"""
    harness_ref = None

    # 处理用户响应
    handle_user_response(response, session, pending_tool_call_id)

    await trigger_hook(hook_registry, HookPoint.SESSION_RESUME, {
        "reason": "user_input_received", "response": response.to_dict(),
    })

    iteration = 0
    final_response: str = ""

    try:
        while iteration < max_iterations:
            cancel_result = check_and_handle_cancel(signal, session, iteration)
            if cancel_result:
                return cancel_result

            iteration += 1

            iteration_result = await run_single_iteration(
                iteration, max_iterations, session, harness_ref, llm_client, sandbox,
                hook_registry, metrics_deque, context_engineering, context_window,
                current_task, system_prompt, enable_pruning, priority, signal,
            )

            if iteration_result.get("status") == "waiting_for_user":
                return iteration_result

            if iteration_result.get("should_exit"):
                final_response = iteration_result.get("content", "")
                break

        if iteration >= max_iterations:
            session.record_session_end("max_iterations_exceeded")
            raise Exception(f"Max iterations exceeded ({iteration})")

        await trigger_hook(hook_registry, HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "completed", final_response=final_response))

        session.record_session_end("completed")
        return {
            "status": "completed", "content": final_response,
            "pending_request": None, "cancel_reason": None, "iterations": iteration,
        }

    except Exception as e:
        await trigger_hook(hook_registry, HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)))
        session.record_session_end("error")
        raise


__all__ = ["resume_with_user_response"]