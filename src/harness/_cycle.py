"""
Harness 核心循环模块

提取 run_cycle 和 run_conversation 的核心逻辑。

内容:
- run_cycle_impl - 执行一轮对话循环
- run_conversation_impl - 执行完整对话
"""

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority
from src.session_event_stream import EventType
from src.tools.builtin_tools import get_pending_ask_user_request, clear_ask_user_state

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import (
    build_llm_call_after_ctx,
    build_llm_call_before_ctx,
    build_response_after_ctx,
    build_response_before_ctx,
    build_session_end_ctx,
    build_session_start_ctx,
    trigger_hook,
)
from ._metrics import ToolExecutionMetrics
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream
    from src.context_engineering import ContextEngineering
    from src.lifecycle_hooks import LifecycleHookRegistry

logger = logging.getLogger(__name__)


def _check_cancelled(signal: AbortSignal | None) -> bool:
    """检查取消信号"""
    return signal is not None and signal.aborted


def _get_cancel_reason(signal: AbortSignal | None) -> str:
    """获取取消原因"""
    return signal.reason if signal else "unknown"


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
    # 1. 检查取消信号
    if _check_cancelled(signal):
        return {
            "status": "cancelled",
            "response": None,
            "tool_results": None,
            "continue_loop": False,
            "pending_request": None,
            "cancel_reason": _get_cancel_reason(signal),
        }

    # 2. 构建上下文
    context = build_context_from_session(
        session, context_engineering, context_window, current_task, system_prompt, enable_pruning
    )
    tools = sandbox.get_tool_schemas()

    # 3. 触发钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_BEFORE,
        build_llm_call_before_ctx(session, harness_ref, context, llm_client.model_id, context_window, tools),
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
            "response": None,
            "tool_results": None,
            "continue_loop": False,
            "pending_request": None,
            "cancel_reason": _get_cancel_reason(signal),
        }

    # 5. 调用 LLM
    start_time = time.time()
    response = await llm_client.reason(context, tools=tools, priority=priority)
    duration_ms = (time.time() - start_time) * 1000

    # 6. 触发 llm_call_after 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.LLM_CALL_AFTER,
        build_llm_call_after_ctx(session, harness_ref, response, duration_ms),
    )

    # 7. 解析响应
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

    # 8. 记录 LLM 响应事件
    llm_data: dict[str, Any] = {}
    if message.get("content"):
        llm_data["content"] = message["content"]
    if message.get("tool_calls"):
        llm_data["tool_calls"] = message["tool_calls"]
    session.emit_event(EventType.LLM_RESPONSE, llm_data)

    # 9. 处理工具调用
    if message.get("tool_calls"):
        tool_results = await route_tool_calls_with_hooks(
            message["tool_calls"], session, harness_ref, sandbox, hook_registry, metrics_deque
        )

        pending_request = get_pending_ask_user_request()
        if pending_request:
            if autonomous_mode:
                # 自主模式：自动跳过
                logger.info(f"Autonomous mode: skipping ask_user request")
                clear_ask_user_state()
                session.emit_event(
                    EventType.USER_RESPONSE,
                    {"request_id": pending_request.request_id, "autonomous_skip": True},
                )
                first_tool_call_id = message["tool_calls"][0].get("id")
                for result in tool_results:
                    if result.get("tool_call_id") == first_tool_call_id:
                        result["content"] = ask_user_skip_response
                await trigger_hook(hook_registry, HookPoint.SESSION_RESUME, {"reason": "autonomous_skip"})
                return {
                    "status": "continue",
                    "response": response,
                    "tool_results": tool_results,
                    "continue_loop": True,
                    "pending_request": None,
                    "cancel_reason": None,
                }

            # 正常模式：等待用户
            session.emit_event(EventType.USER_WAITING, {"request": pending_request.to_dict()})
            await trigger_hook(
                hook_registry,
                HookPoint.SESSION_PAUSE,
                {"reason": "user_input_required", "request": pending_request.to_dict()},
            )
            return {
                "status": "waiting_for_user",
                "response": response,
                "tool_results": tool_results,
                "continue_loop": False,
                "pending_request": pending_request.to_dict(),
                "cancel_reason": None,
            }

        # 记录工具结果
        for result in tool_results:
            session.emit_event(
                EventType.TOOL_RESULT,
                {"tool_call_id": result["tool_call_id"], "content": result["content"]},
            )

        await trigger_hook(
            hook_registry,
            HookPoint.RESPONSE_AFTER,
            build_response_after_ctx(session, harness_ref, response, True),
        )
        return {
            "status": "continue",
            "response": response,
            "tool_results": tool_results,
            "continue_loop": True,
            "pending_request": None,
            "cancel_reason": None,
        }

    # 无工具调用 = 完成
    await trigger_hook(
        hook_registry,
        HookPoint.RESPONSE_AFTER,
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