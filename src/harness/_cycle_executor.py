"""Harness 单轮循环执行器

包含 run_cycle_impl 函数，执行一轮对话循环。

内容:
- run_cycle_impl - 执行一轮对话循环
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.request_queue import RequestPriority
from src.session_event_stream import EventType

from ._cycle_prepare import call_llm, prepare_cycle
from ._cycle_tool_handling import handle_tool_calls
from ._cycle_utils import _check_cancelled, _get_cancel_reason
from ._lifecycle_hooks import build_response_after_ctx, trigger_hook
from ._metrics import ToolExecutionMetrics

if TYPE_CHECKING:
    from src.context_engineering import ContextEngineering
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def run_cycle_impl(
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
    priority: int = RequestPriority.NORMAL,
    signal: AbortSignal | None = None,
) -> dict[str, Any]:
    """执行一轮对话循环

    Args:
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
        CycleResult 字典
    """
    # 1. 准备阶段
    prep_result = await prepare_cycle(
        llm_client, session, hook_registry, max_iterations,
        context_window, context_engineering, current_task,
        system_prompt, enable_pruning, harness_ref, priority, signal
    )

    if prep_result and prep_result.get("status") == "cancelled":
        return {
            "status": "cancelled",
            "response": None,
            "tool_results": None,
            "continue_loop": False,
            "pending_request": None,
            "cancel_reason": prep_result["cancel_reason"],
        }

    context = prep_result["context"] if prep_result else []

    # 2. 调用 LLM
    response, _ = await call_llm(
        llm_client, session, sandbox, hook_registry, harness_ref, context, priority
    )

    # 3. 解析响应
    choices = response.get("choices", [])
    if not choices:
        return {
            "status": "complete",
            "response": None,
            "tool_results": None,
            "continue_loop": False,
            "pending_request": None,
            "cancel_reason": None,
        }

    message = choices[0].get("message", {})

    # 4. 记录 LLM 响应事件
    llm_data: dict[str, Any] = {}
    if message.get("content"):
        llm_data["content"] = message["content"]
    if message.get("tool_calls"):
        llm_data["tool_calls"] = message["tool_calls"]
    session.emit_event(EventType.LLM_RESPONSE, llm_data)

    # 5. 处理工具调用
    if message.get("tool_calls"):
        tool_result = await handle_tool_calls(
            message, session, sandbox, hook_registry, harness_ref,
            metrics_deque, autonomous_mode, ask_user_skip_response, response
        )

        if tool_result["status"] == "waiting_for_user":
            return {
                "status": "waiting_for_user",
                "response": response,
                "tool_results": tool_result["tool_results"],
                "continue_loop": False,
                "pending_request": tool_result["pending_request"],
                "cancel_reason": None,
            }

        if tool_result["status"] == "continue":
            return {
                "status": "continue",
                "response": response,
                "tool_results": tool_result["tool_results"],
                "continue_loop": True,
                "pending_request": None,
                "cancel_reason": None,
            }

    # 6. 无工具调用 = 完成
    await trigger_hook(
        hook_registry,
        "RESPONSE_AFTER",
        build_response_after_ctx(session, harness_ref, response, False),
    )
    return {
        "status": "complete",
        "response": response,
        "tool_results": None,
        "continue_loop": False,
        "pending_request": None,
        "cancel_reason": None,
    }