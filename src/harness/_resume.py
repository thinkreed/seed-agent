"""
Harness 恢复执行模块

提取用户响应后恢复执行的逻辑。

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
from src.tools.builtin_tools import clear_ask_user_state

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import build_session_end_ctx, trigger_hook
from ._metrics import ToolExecutionMetrics
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream
    from src.tools.ask_user_types import AskUserResult
    from src.lifecycle_hooks import LifecycleHookRegistry

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
        dict: 执行结果
            - status: "completed" | "waiting_for_user" | "cancelled" | "max_iterations"
            - content: 最终响应文本（完成时）
            - pending_request: Ask User 请求（等待时）
            - cancel_reason: 取消原因（取消时）
            - iterations: 执行的迭代次数
    """
    harness_ref = None  # Will be set by caller if needed

    # Helper functions for cancel check
    def _check_cancelled(sig: AbortSignal | None) -> bool:
        return sig is not None and sig.aborted

    def _get_cancel_reason(sig: AbortSignal | None) -> str:
        return sig.reason if sig else "unknown"

    # 1. 清理等待状态
    clear_ask_user_state()

    # 2. 记录用户响应事件
    session.emit_event(
        EventType.USER_RESPONSE,
        {
            "request_id": response.request_id,
            "responses": [r.to_dict() for r in response.responses],
            "cancelled": response.cancelled,
            "timeout": response.timeout,
        },
    )

    # 3. 触发 SESSION_RESUME 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.SESSION_RESUME,
        {"reason": "user_input_received", "response": response.to_dict()},
    )

    # 4. 构造工具结果并注入历史
    if response.cancelled:
        tool_result = "[USER_CANCELLED]"
    elif response.timeout:
        tool_result = "[USER_TIMEOUT]"
    else:
        selected = response.get_selected_values()
        tool_result = f"User selected: {selected}"

    # 5. 注入到历史（作为 tool result）
    if pending_tool_call_id:
        session.emit_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": pending_tool_call_id, "content": tool_result},
        )

    # 6. 继续执行循环
    iteration = 0
    final_response: str = ""

    try:
        while iteration < max_iterations:
            # 每轮开始检查取消信号
            if _check_cancelled(signal):
                session.emit_event(
                    EventType.EXECUTION_CANCEL,
                    {"reason": _get_cancel_reason(signal), "iteration": iteration},
                )
                return {
                    "status": "cancelled",
                    "content": "",
                    "pending_request": None,
                    "cancel_reason": _get_cancel_reason(signal),
                    "iterations": iteration,
                }

            iteration += 1
            logger.debug(f"Harness iteration {iteration}/{max_iterations} (resumed)")

            # 构建上下文
            context = build_context_from_session(
                session,
                context_engineering,
                context_window,
                current_task,
                system_prompt,
                enable_pruning,
            )

            # 触发 llm_call_before 钩子
            tools = sandbox.get_tool_schemas()
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

            # 触发 response_before 钩子
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
            if _check_cancelled(signal):
                return {
                    "status": "cancelled",
                    "content": "",
                    "pending_request": None,
                    "cancel_reason": _get_cancel_reason(signal),
                    "iterations": iteration,
                }

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

            # 解析响应
            choices = resp.get("choices", [])
            if not choices:
                logger.warning("LLM response has empty choices")
                return {
                    "status": "complete",
                    "response": None,
                    "tool_results": None,
                    "continue_loop": False,
                    "pending_request": None,
                    "cancel_reason": None,
                }
            choice = choices[0]
            message = choice.get("message", {})

            # 记录 LLM 响应事件
            llm_data: dict[str, Any] = {}
            if message.get("content"):
                llm_data["content"] = message["content"]
            if message.get("tool_calls"):
                llm_data["tool_calls"] = message["tool_calls"]

            session.emit_event(EventType.LLM_RESPONSE, llm_data)

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
                from src.tools.builtin_tools import get_pending_ask_user_request
                pending_request = get_pending_ask_user_request()
                if pending_request:
                    session.emit_event(
                        EventType.USER_WAITING,
                        {
                            "request": pending_request.to_dict(),
                            "tool_call_id": message["tool_calls"][0].get("id"),
                        },
                    )
                    await trigger_hook(
                        hook_registry,
                        HookPoint.SESSION_PAUSE,
                        {
                            "reason": "user_input_required",
                            "request": pending_request.to_dict(),
                        },
                    )
                    return {
                        "status": "waiting_for_user",
                        "content": "",
                        "pending_request": pending_request.to_dict(),
                        "cancel_reason": None,
                        "iterations": iteration,
                    }

                # 记录工具结果事件
                for result in tool_results:
                    session.emit_event(
                        EventType.TOOL_RESULT,
                        {
                            "tool_call_id": result["tool_call_id"],
                            "content": result["content"],
                        },
                    )

                # 触发 response_after 钩子（继续）
                await trigger_hook(
                    hook_registry,
                    HookPoint.RESPONSE_AFTER,
                    {
                        "session": session,
                        "harness": harness_ref,
                        "response": resp,
                        "should_continue": True,
                    },
                )
            else:
                # 触发 response_after 钩子（完成）
                await trigger_hook(
                    hook_registry,
                    HookPoint.RESPONSE_AFTER,
                    {
                        "session": session,
                        "harness": harness_ref,
                        "response": resp,
                        "should_continue": False,
                    },
                )

                # 无工具调用 = 对话完成
                if resp:
                    if choices:
                        final_response = choices[0].get("message", {}).get("content", "")
                break

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