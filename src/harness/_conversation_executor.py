"""Harness 对话执行器

包含 run_conversation_impl 函数，执行完整对话。
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority
from src.session_event_stream import EventType

from ._cycle_executor import run_cycle_impl
from ._cycle_utils import _check_cancelled, _get_cancel_reason
from ._lifecycle_hooks import build_session_end_ctx, build_session_start_ctx, trigger_hook
from ._metrics import ToolExecutionMetrics

if TYPE_CHECKING:
    from src.context_engineering import ContextEngineering
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def run_conversation_impl(
    initial_prompt: str,
    llm_client: "LLMClient",
    session: "SessionEventStream",
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
    metrics_deque: deque[ToolExecutionMetrics],
    max_iterations: int,
    context_window: int,
    context_engineering: "ContextEngineering | None",
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    autonomous_mode: bool,
    ask_user_skip_response: str,
    harness_ref: Any,
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
) -> dict[str, Any]:
    """执行完整对话"""
    await trigger_hook(
        hook_registry, HookPoint.SESSION_START,
        build_session_start_ctx(session, harness_ref, initial_prompt),
    )
    session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

    iteration = 0
    final_response = ""

    try:
        while iteration < max_iterations:
            if _check_cancelled(signal):
                reason = _get_cancel_reason(signal)
                session.emit_event(EventType.EXECUTION_CANCEL, {"reason": reason, "iteration": iteration})
                return {"status": "cancelled", "content": "", "cancel_reason": reason, "iterations": iteration}

            iteration += 1
            cycle_result = await run_cycle_impl(
                llm_client, session, sandbox, hook_registry, metrics_deque, max_iterations,
                context_window, context_engineering, current_task, system_prompt,
                enable_pruning, autonomous_mode, ask_user_skip_response, harness_ref, priority, signal,
            )

            if cycle_result["status"] == "cancelled":
                return {"status": "cancelled", "cancel_reason": cycle_result["cancel_reason"], "iterations": iteration}
            if cycle_result["status"] == "waiting_for_user":
                return {"status": "waiting_for_user", "pending_request": cycle_result["pending_request"], "iterations": iteration}
            if cycle_result["status"] == "complete":
                resp = cycle_result.get("response")
                if resp and resp.get("choices"):
                    final_response = resp["choices"][0].get("message", {}).get("content", "")
                break

        if iteration >= max_iterations:
            session.record_session_end("max_iterations_exceeded")
            raise RuntimeError(f"MaxIterationsExceeded:{iteration}")

        await _end_session(hook_registry, session, harness_ref, "completed", final_response=final_response)
        return {"status": "completed", "content": final_response, "iterations": iteration}

    except RuntimeError as e:
        if str(e).startswith("MaxIterationsExceeded:"):
            raise
        await _end_session(hook_registry, session, harness_ref, "error", error=str(e))
        raise
    except Exception as e:
        await _end_session(hook_registry, session, harness_ref, "error", error=str(e))
        raise


async def _end_session(
    hook_registry: "LifecycleHookRegistry | None",
    session: "SessionEventStream",
    harness_ref: Any,
    status: str,
    final_response: str = "",
    error: str = "",
) -> None:
    """结束会话并触发钩子"""
    ctx = build_session_end_ctx(session, harness_ref, status, final_response=final_response, error=error)
    await trigger_hook(hook_registry, HookPoint.SESSION_END, ctx)
    session.record_session_end(status)