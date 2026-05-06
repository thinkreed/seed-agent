"""Harness 单轮迭代逻辑"""

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import trigger_hook
from ._metrics import ToolExecutionMetrics
from ._resume_utils import check_and_handle_cancel, handle_tool_calls_result, process_llm_response
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def run_single_iteration(
    iteration: int,
    max_iterations: int,
    session: "SessionEventStream",
    harness_ref: Any,
    llm_client: "LLMClient",
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
    metrics_deque: deque[ToolExecutionMetrics],
    context_engineering: Any,
    context_window: int,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    priority: int,
    signal: AbortSignal | None,
) -> dict[str, Any]:
    """执行单轮迭代"""
    # 构建上下文
    context = build_context_from_session(
        session, context_engineering, context_window, current_task, system_prompt, enable_pruning
    )
    tools = sandbox.get_tool_schemas()

    # 触发钩子
    await trigger_hook(hook_registry, HookPoint.LLM_CALL_BEFORE, {
        "session": session, "harness": harness_ref, "messages": context,
        "model_id": llm_client.model_id, "context_window": context_window, "tools": tools,
    })
    await trigger_hook(hook_registry, HookPoint.RESPONSE_BEFORE, {
        "session": session, "harness": harness_ref, "iteration": iteration, "max_iterations": max_iterations,
    })

    # 检查取消信号
    cancel_result = check_and_handle_cancel(signal, session, iteration)
    if cancel_result:
        return cancel_result

    # 调用 LLM 推理
    start_time = time.time()
    resp = await llm_client.reason(context, tools=tools, priority=priority)
    duration_ms = (time.time() - start_time) * 1000

    await trigger_hook(hook_registry, HookPoint.LLM_CALL_AFTER, {
        "session": session, "harness": harness_ref, "response": resp, "duration_ms": duration_ms,
    })

    # 处理响应
    text_content, message, _ = process_llm_response(resp, session)

    # 处理工具调用
    if message.get("tool_calls"):
        tool_results = await route_tool_calls_with_hooks(
            message["tool_calls"], session, harness_ref, sandbox, hook_registry, metrics_deque
        )

        wait_result = await handle_tool_calls_result(tool_results, session)
        if wait_result:
            await trigger_hook(hook_registry, HookPoint.SESSION_PAUSE, {
                "reason": "user_input_required", "request": wait_result["pending_request"].to_dict(),
            })
            return {
                "status": "waiting_for_user", "content": "",
                "pending_request": wait_result["pending_request"].to_dict(),
                "cancel_reason": None, "iterations": iteration,
            }

        await trigger_hook(hook_registry, HookPoint.RESPONSE_AFTER, {
            "session": session, "harness": harness_ref, "response": resp, "should_continue": True,
        })
        return {"should_exit": False}

    # 无工具调用 = 对话完成
    await trigger_hook(hook_registry, HookPoint.RESPONSE_AFTER, {
        "session": session, "harness": harness_ref, "response": resp, "should_continue": False,
    })
    return {"should_exit": True, "content": text_content}


__all__ = ["run_single_iteration"]