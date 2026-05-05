"""
Harness 流式处理模块

提取流式对话处理逻辑。

内容:
- stream_conversation - 流式执行对话
- stream_resume_with_user_response - 流式恢复执行
- process_tool_delta - 处理流式 Tool Call 增量
"""

import logging
import time
from collections import deque
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.lifecycle_hooks import HookPoint
from src.request_queue import RequestPriority
from src.session_event_stream import EventType
from src.tools.builtin_tools import clear_ask_user_state, get_pending_ask_user_request

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import (
    build_llm_call_after_ctx,
    build_response_after_ctx,
    build_response_before_ctx,
    build_session_end_ctx,
    build_session_start_ctx,
    trigger_hook,
)
from ._metrics import ToolExecutionMetrics
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)


def process_tool_delta(
    tc_list: list[dict[str, Any]],
    accumulator: dict[int, dict[str, Any]],
) -> None:
    """处理流式 Tool Call 增量

    Args:
        tc_list: Tool Call 增量列表
        accumulator: 累积器字典
    """
    for tc in tc_list:
        idx = tc.get("index", 0)
        if idx not in accumulator:
            accumulator[idx] = {
                "id": tc.get("id"),
                "type": tc.get("type", "function"),
                "function": {"name": "", "arguments": ""},
            }
        acc = accumulator[idx]
        if tc.get("id"):
            acc["id"] = tc["id"]
        if tc.get("type"):
            acc["type"] = tc["type"]
        func = tc.get("function", {})
        if func.get("name"):
            acc["function"]["name"] = func["name"]
        if func.get("arguments"):
            acc["function"]["arguments"] += func["arguments"]


async def stream_conversation(
    initial_prompt: str,
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
    autonomous_mode: bool,
    ask_user_skip_response: str,
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """流式执行对话（支持取消信号、Ask User、生命周期钩子）

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
        priority: 请求优先级
        signal: 取消信号

    Yields:
        流式响应 chunk:
            - {"type": "chunk", "content": "..."} - 文本片段
            - {"type": "tool_start", "tool_name": "..."} - 工具开始
            - {"type": "tool_end", "result": "..."} - 工具结束
            - {"type": "awaiting_user_input", "request": {...}} - 等待用户输入
            - {"type": "cancelled", "reason": "..."} - 执行取消
            - {"type": "final", "content": "..."} - 最终响应
            - {"type": "error", "content": "..."} - 错误
    """
    harness_ref = None  # Will be set by caller if needed

    # 1. 触发 session_start 钩子
    await trigger_hook(
        hook_registry,
        HookPoint.SESSION_START,
        build_session_start_ctx(session, harness_ref, initial_prompt),
    )

    # 2. 记录初始输入
    session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

    iteration = 0

    # Helper functions for cancel check
    def _check_cancelled(sig: AbortSignal | None) -> bool:
        return sig is not None and sig.aborted

    def _get_cancel_reason(sig: AbortSignal | None) -> str:
        return sig.reason if sig else "unknown"

    try:
        while iteration < max_iterations:
            # 每轮开始检查取消信号
            if _check_cancelled(signal):
                session.emit_event(
                    EventType.EXECUTION_CANCEL,
                    {"reason": _get_cancel_reason(signal), "iteration": iteration},
                )
                yield {"type": "cancelled", "reason": _get_cancel_reason(signal)}
                return

            iteration += 1
            logger.debug(f"stream_conversation iteration {iteration}/{max_iterations}")

            # 3. 构建上下文
            context = build_context_from_session(
                session,
                context_engineering,
                context_window,
                current_task,
                system_prompt,
                enable_pruning,
            )
            tools = sandbox.get_tool_schemas()

            # 4. 触发钩子
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
                build_response_before_ctx(session, harness_ref, iteration, max_iterations),
            )

            # 5. 再次检查取消信号
            if _check_cancelled(signal):
                yield {"type": "cancelled", "reason": _get_cancel_reason(signal)}
                return

            # 6. 流式推理
            start_time = time.time()
            full_content = ""
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in llm_client.stream_reason(context, tools=tools, priority=priority):
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get("tool_calls")
                if tc_list:
                    process_tool_delta(tc_list, tool_calls_accumulator)
                    for tc in tc_list:
                        if tc.get("function", {}).get("name"):
                            yield {"type": "tool_start", "tool_name": tc["function"]["name"]}

            duration_ms = (time.time() - start_time) * 1000

            # 7. 触发 llm_call_after 钩子
            await trigger_hook(
                hook_registry,
                HookPoint.LLM_CALL_AFTER,
                build_llm_call_after_ctx(
                    session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, duration_ms
                ),
            )

            # 8. 累积工具调用
            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator
                else []
            )

            # 9. 记录响应
            llm_data: dict[str, Any] = {}
            if full_content:
                llm_data["content"] = full_content
            if tool_calls:
                llm_data["tool_calls"] = tool_calls

            session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 10. 执行工具或完成
            if tool_calls:
                tool_results = await route_tool_calls_with_hooks(
                    tool_calls, session, harness_ref, sandbox, hook_registry, metrics_deque
                )

                # 检查 ask_user 等待
                pending_request = get_pending_ask_user_request()
                if pending_request:
                    # 自主模式：自动跳过
                    if autonomous_mode:
                        logger.info(f"Autonomous mode: skipping ask_user request {pending_request.request_id}")
                        clear_ask_user_state()
                        session.emit_event(
                            EventType.USER_RESPONSE,
                            {
                                "request_id": pending_request.request_id,
                                "responses": [],
                                "cancelled": False,
                                "timeout": False,
                                "autonomous_skip": True,
                                "skip_reason": "autonomous_mode",
                            },
                        )
                        first_tool_call_id = tool_calls[0].get("id")
                        for result in tool_results:
                            if result.get("tool_call_id") == first_tool_call_id:
                                result["content"] = ask_user_skip_response
                        session.emit_event(
                            EventType.TOOL_RESULT,
                            {"tool_call_id": first_tool_call_id, "content": ask_user_skip_response},
                        )
                        await trigger_hook(
                            hook_registry,
                            HookPoint.SESSION_RESUME,
                            {"reason": "autonomous_skip", "request": pending_request.to_dict()},
                        )
                        # 继续循环
                        continue

                    # 正常模式：等待用户响应
                    session.emit_event(
                        EventType.USER_WAITING,
                        {"request": pending_request.to_dict(), "tool_call_id": tool_calls[0].get("id")},
                    )
                    await trigger_hook(
                        hook_registry,
                        HookPoint.SESSION_PAUSE,
                        {"reason": "user_input_required", "request": pending_request.to_dict()},
                    )
                    yield {"type": "awaiting_user_input", "request": pending_request.to_dict()}
                    return

                for result in tool_results:
                    session.emit_event(
                        EventType.TOOL_RESULT,
                        {"tool_call_id": result["tool_call_id"], "content": result["content"]},
                    )
                    yield {"type": "tool_end", "result": result["content"]}

                await trigger_hook(
                    hook_registry,
                    HookPoint.RESPONSE_AFTER,
                    build_response_after_ctx(
                        session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, True
                    ),
                )
            else:
                # 无工具调用 = 完成
                await trigger_hook(
                    hook_registry,
                    HookPoint.RESPONSE_AFTER,
                    build_response_after_ctx(
                        session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, False
                    ),
                )
                await trigger_hook(
                    hook_registry,
                    HookPoint.SESSION_END,
                    build_session_end_ctx(session, harness_ref, "completed", final_response=full_content),
                )
                session.record_session_end("completed")
                yield {"type": "final", "content": full_content}
                return

        # 超过最大迭代
        session.record_session_end("max_iterations_exceeded")
        raise Exception(f"Max iterations exceeded ({max_iterations})")

    except Exception as e:
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)),
        )
        session.record_session_end("error")
        yield {"type": "error", "content": str(e)}


async def stream_resume_with_user_response(
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
) -> AsyncGenerator[dict[str, Any], None]:
    """流式恢复执行（用户响应后）

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

    Yields:
        流式响应 chunk（同 stream_conversation）
    """
    harness_ref = None

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

    # 4. 构造工具结果
    if response.cancelled:
        tool_result = "[USER_CANCELLED]"
    elif response.timeout:
        tool_result = "[USER_TIMEOUT]"
    else:
        selected = response.get_selected_values()
        tool_result = f"User selected: {selected}"

    # 5. 注入到历史
    if pending_tool_call_id:
        session.emit_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": pending_tool_call_id, "content": tool_result},
        )

    # 6. 继续执行循环
    iteration = 0
    try:
        while iteration < max_iterations:
            if _check_cancelled(signal):
                session.emit_event(
                    EventType.EXECUTION_CANCEL,
                    {"reason": _get_cancel_reason(signal), "iteration": iteration},
                )
                yield {"type": "cancelled", "reason": _get_cancel_reason(signal)}
                return

            iteration += 1
            logger.debug(f"stream_resume iteration {iteration}/{max_iterations}")

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

            # 流式推理
            start_time = time.time()
            full_content = ""
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in llm_client.stream_reason(context, tools=tools, priority=priority):
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get("tool_calls")
                if tc_list:
                    process_tool_delta(tc_list, tool_calls_accumulator)
                    for tc in tc_list:
                        if tc.get("function", {}).get("name"):
                            yield {"type": "tool_start", "tool_name": tc["function"]["name"]}

            duration_ms = (time.time() - start_time) * 1000

            # 触发 llm_call_after 钩子
            await trigger_hook(
                hook_registry,
                HookPoint.LLM_CALL_AFTER,
                build_llm_call_after_ctx(
                    session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, duration_ms
                ),
            )

            # 累积工具调用
            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator
                else []
            )

            # 记录响应
            llm_data: dict[str, Any] = {}
            if full_content:
                llm_data["content"] = full_content
            if tool_calls:
                llm_data["tool_calls"] = tool_calls

            session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 执行工具或完成
            if tool_calls:
                tool_results = await route_tool_calls_with_hooks(
                    tool_calls, session, harness_ref, sandbox, hook_registry, metrics_deque
                )

                pending_request = get_pending_ask_user_request()
                if pending_request:
                    session.emit_event(
                        EventType.USER_WAITING,
                        {"request": pending_request.to_dict(), "tool_call_id": tool_calls[0].get("id")},
                    )
                    await trigger_hook(
                        hook_registry,
                        HookPoint.SESSION_PAUSE,
                        {"reason": "user_input_required", "request": pending_request.to_dict()},
                    )
                    yield {"type": "awaiting_user_input", "request": pending_request.to_dict()}
                    return

                for result in tool_results:
                    session.emit_event(
                        EventType.TOOL_RESULT,
                        {"tool_call_id": result["tool_call_id"], "content": result["content"]},
                    )
                    yield {"type": "tool_end", "result": result["content"]}
            else:
                # 完成
                await trigger_hook(
                    hook_registry,
                    HookPoint.SESSION_END,
                    build_session_end_ctx(session, harness_ref, "completed", final_response=full_content),
                )
                session.record_session_end("completed")
                yield {"type": "final", "content": full_content}
                return

        session.record_session_end("max_iterations_exceeded")
        raise Exception(f"Max iterations exceeded ({max_iterations})")

    except Exception as e:
        await trigger_hook(
            hook_registry,
            HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "error", error=str(e)),
        )
        session.record_session_end("error")
        yield {"type": "error", "content": str(e)}