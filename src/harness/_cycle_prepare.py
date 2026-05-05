"""Harness 循环准备阶段

包含上下文构建、钩子触发、取消检查等准备逻辑。
"""

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import (
    build_llm_call_after_ctx,
    build_llm_call_before_ctx,
    build_response_before_ctx,
    trigger_hook,
)
from ._metrics import ToolExecutionMetrics
from ._cycle_utils import _check_cancelled, _get_cancel_reason

if TYPE_CHECKING:
    from src.context_engineering import ContextEngineering
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def prepare_cycle(
    llm_client: "LLMClient",
    session: "SessionEventStream",
    hook_registry: "LifecycleHookRegistry | None",
    max_iterations: int,
    context_window: int,
    context_engineering: "ContextEngineering | None",
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    harness_ref: Any,
    priority: int,
    signal: AbortSignal | None,
) -> dict[str, Any] | None:
    """准备一轮对话循环

    Returns:
        None if cancelled, otherwise preparation result dict
    """
    # 1. 检查取消信号
    if _check_cancelled(signal):
        return {
            "status": "cancelled",
            "cancel_reason": _get_cancel_reason(signal),
        }

    # 2. 构建上下文
    context = build_context_from_session(
        session, context_engineering, context_window, current_task, system_prompt, enable_pruning
    )

    # 3. 触发钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_BEFORE,
        build_llm_call_before_ctx(session, harness_ref, context, llm_client.model_id, context_window, []),
    )
    await trigger_hook(
        hook_registry,
        HookPoint.RESPONSE_BEFORE,
        build_response_before_ctx(session, harness_ref, 0, max_iterations),
    )

    # 4. 再次检查取消
    if _check_cancelled(signal):
        return {
            "status": "cancelled",
            "cancel_reason": _get_cancel_reason(signal),
        }

    return {
        "status": "prepared",
        "context": context,
    }


async def call_llm(
    llm_client: "LLMClient",
    session: "SessionEventStream",
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
    harness_ref: Any,
    context: list,
    priority: int,
) -> tuple[dict, float]:
    """调用 LLM 并返回响应

    Returns:
        (response, duration_ms)
    """
    tools = sandbox.get_tool_schemas()

    start_time = time.time()
    response = await llm_client.reason(context, tools=tools, priority=priority)
    duration_ms = (time.time() - start_time) * 1000

    # 触发 llm_call_after 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_AFTER,
        build_llm_call_after_ctx(session, harness_ref, response, duration_ms),
    )

    return response, duration_ms