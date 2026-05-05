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
from ._lifecycle_hooks import (
    build_session_end_ctx,
    build_session_start_ctx,
    trigger_hook,
)
from ._metrics import ToolExecutionMetrics
from ._cycle_utils import _check_cancelled, _get_cancel_reason

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
    """执行完整对话

    Args:
        initial_prompt: 用户输入
        llm_client: LLMClient 实例
        session: SessionEventStream 实例
        sandbox: Sandbox 实例
        hook_registry: 钩子注册中心
        metrics_deque: 指标存储 deque
        max_iterations: 最大迭代次数
        context_window: 上下文窗口大小
        context_engineering: 上下文工程实例
        current_task: 当前任务描述
        system_prompt: 系统提示
        enable_pruning: 是否启用智能裁剪
        autonomous_mode: 自主模式
        ask_user_skip_response: 自主模式跳过响应
        harness_ref: Harness 实例引用
        priority: 请求优先级
        signal: 取消信号

    Returns:
        执行结果字典
    """
    # 触发 session_start 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.SESSION_START,
        build_session_start_ctx(session, harness_ref, initial_prompt),
    )

    # 记录初始输入
    session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

    iteration = 0
    final_response: str = ""

    try:
        while iteration < max_iterations:
            if _check_cancelled(signal):
                session.emit_event(
                    EventType.EXECUTION_CANCEL,
                    {"reason": _get_cancel_reason(signal), "iteration": iteration},
                )
                return {
                    "status": "cancelled",
                    "content": "",
                    "cancel_reason": _get_cancel_reason(signal),
                    "iterations": iteration,
                }

            iteration += 1
            cycle_result = await run_cycle_impl(
                llm_client,
                session,
                sandbox,
                hook_registry,
                metrics_deque,
                max_iterations,
                context_window,
                context_engineering,
                current_task,
                system_prompt,
                enable_pruning,
                autonomous_mode,
                ask_user_skip_response,
                harness_ref,
                priority,
                signal,
            )

            if cycle_result["status"] == "cancelled":
                return {
                    "status": "cancelled",
                    "cancel_reason": cycle_result["cancel_reason"],
                    "iterations": iteration,
                }

            if cycle_result["status"] == "waiting_for_user":
                return {
                    "status": "waiting_for_user",
                    "pending_request": cycle_result["pending_request"],
                    "iterations": iteration,
                }

            if cycle_result["status"] == "complete":
                resp = cycle_result["response"]
                if resp:
                    choices = resp.get("choices", [])
                    if choices:
                        final_response = choices[0].get("message", {}).get("content", "")
                break

        if iteration >= max_iterations:
            session.record_session_end("max_iterations_exceeded")
            # 使用通用异常，让主文件捕获并转换为 MaxIterationsExceededError
            raise RuntimeError(f"MaxIterationsExceeded:{iteration}")

        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "completed", final_response=final_response),
        )
        session.record_session_end("completed")
        return {
            "status": "completed",
            "content": final_response,
            "iterations": iteration,
        }

    except RuntimeError as e:
        if str(e).startswith("MaxIterationsExceeded:"):
            # 重新抛出，让主文件处理
            raise
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)),
        )
        session.record_session_end("error")
        raise
    except Exception as e:
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)),
        )
        session.record_session_end("error")
        raise