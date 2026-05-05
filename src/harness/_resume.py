"""Harness 恢复执行模块（重构版）

简化后的恢复执行逻辑，使用辅助函数拆分。

内容:
- resume_with_user_response - 恢复执行（用户响应后）
"""

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority
from src.session_event_stream import EventType

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import build_session_end_ctx, trigger_hook
from ._metrics import ToolExecutionMetrics
from ._resume_utils import (
    check_and_handle_cancel,
    handle_tool_calls_result,
    handle_user_response,
    process_llm_response,
)
from ._tool_router import route_tool_calls_with_hooks

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
    """恢复执行（用户响应后）

    Args:
        response: 用户响应数据
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
        pending_tool_call_id: 等待的工具调用 ID
        priority: 请求优先级
        signal: 取消信号

    Returns:
        执行结果 dict
    """
    harness_ref = None

    # 1. 处理用户响应并注入历史
    handle_user_response(response, session, pending_tool_call_id)

    # 2. 触发 SESSION_RESUME 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.SESSION_RESUME,
        {"reason": "user_input_received", "response": response.to_dict()},
    )

    # 3. 执行循环
    iteration = 0
    final_response: str = ""

    try:
        while iteration < max_iterations:
            # 检查取消信号
            cancel_result = check_and_handle_cancel(signal, session, iteration)
            if cancel_result:
                return cancel_result

            iteration += 1
            logger.debug(f"Harness iteration {iteration}/{max_iterations} (resumed)")

            # 执行单轮迭代
            iteration_result = await _run_single_iteration(
                iteration,
                max_iterations,
                session,
                harness_ref,
                llm_client,
                sandbox,
                hook_registry,
                metrics_deque,
                context_engineering,
                context_window,
                current_task,
                system_prompt,
                enable_pruning,
                priority,
                signal,
            )

            # 处理迭代结果
            if iteration_result.get("status") == "waiting_for_user":
                return iteration_result

            if iteration_result.get("should_exit"):
                final_response = iteration_result.get("content", "")
                break

        # 检查是否超过最大迭代
        if iteration >= max_iterations:
            session.record_session_end("max_iterations_exceeded")
            raise Exception(f"Max iterations exceeded ({iteration})")

        # 触发 session_end 钩子（成功）
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "completed", final_response=final_response),
        )

        session.record_session_end("completed")
        return {
            "status": "completed",
            "content": final_response,
            "pending_request": None,
            "cancel_reason": None,
            "iterations": iteration,
        }

    except Exception as e:
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)),
        )
        session.record_session_end("error")
        raise


async def _run_single_iteration(
    iteration: int,
    max_iterations: int,
    session: "SessionEventStream",
    harness_ref: Any,
    llm_client: "LLMClient",
    sandbox: "Sandbox",
    hook_registry: Any,
    metrics_deque: deque[ToolExecutionMetrics],
    context_engineering: Any,
    context_window: int,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    priority: int,
    signal: AbortSignal | None,
) -> dict[str, Any]:
    """执行单轮迭代

    Args:
        iteration: 当前迭代次数
        max_iterations: 最大迭代次数
        其他参数同 resume_with_user_response

    Returns:
        迭代结果 dict
    """
    # 构建上下文
    context = build_context_from_session(
        session,
        context_engineering,
        context_window,
        current_task,
        system_prompt,
        enable_pruning,
    )

    tools = sandbox.get_tool_schemas()

    # 触发钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_BEFORE,
        {
            "session": session,
            "harness": harness_ref,
            "messages": context,
            "model_id": llm_client.model_id,
            "context_window": context_window,
            "tools": tools,
        },
    )

    await trigger_hook(
        hook_registry,
        HookPoint.RESPONSE_BEFORE,
        {
            "session": session,
            "harness": harness_ref,
            "iteration": iteration,
            "max_iterations": max_iterations,
        },
    )

    # 再次检查取消信号
    cancel_result = check_and_handle_cancel(signal, session, iteration)
    if cancel_result:
        return cancel_result

    # 调用 LLM 推理
    start_time = time.time()
    resp = await llm_client.reason(context, tools=tools, priority=priority)
    duration_ms = (time.time() - start_time) * 1000

    # 触发 llm_call_after 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_AFTER,
        {"session": session, "harness": harness_ref, "response": resp, "duration_ms": duration_ms},
    )

    # 处理响应
    text_content, message, _ = process_llm_response(resp, session)

    # 处理工具调用或完成
    if message.get("tool_calls"):
        tool_results = await route_tool_calls_with_hooks(
            message["tool_calls"],
            session,
            harness_ref,
            sandbox,
            hook_registry,
            metrics_deque,
        )

        # 检查是否再次触发了 ask_user 等待
        wait_result = await handle_tool_calls_result(tool_results, session)
        if wait_result:
            await trigger_hook(
                hook_registry,
                HookPoint.SESSION_PAUSE,
                {"reason": "user_input_required", "request": wait_result["pending_request"].to_dict()},
            )
            return {
                "status": "waiting_for_user",
                "content": "",
                "pending_request": wait_result["pending_request"].to_dict(),
                "cancel_reason": None,
                "iterations": iteration,
            }

        # 触发 response_after 钩子（继续）
        await trigger_hook(
            hook_registry,
            HookPoint.RESPONSE_AFTER,
            {"session": session, "harness": harness_ref, "response": resp, "should_continue": True},
        )

        return {"should_exit": False}

    # 无工具调用 = 对话完成
    await trigger_hook(
        hook_registry,
        HookPoint.RESPONSE_AFTER,
        {"session": session, "harness": harness_ref, "response": resp, "should_continue": False},
    )

    return {"should_exit": True, "content": text_content}