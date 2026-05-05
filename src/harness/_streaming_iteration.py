"""
Harness 流式迭代处理器

提取单轮迭代的工具执行和 Ask User 处理逻辑。

内容:
- IterationOutcome - 迭代结果类型枚举
- handle_tool_execution - 处理工具执行和 Ask User
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint
from src.session_event_stream import EventType
from src.tools.builtin_tools import clear_ask_user_state, get_pending_ask_user_request

from ._lifecycle_hooks import build_response_after_ctx, build_session_end_ctx, trigger_hook
from ._streaming_types import IterationResult
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

    from ._metrics import ToolExecutionMetrics

logger = logging.getLogger(__name__)


class IterationOutcome:
    """迭代结果类型"""
    CONTINUE = "continue"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    AUTONOMOUS_SKIP = "autonomous_skip"


async def handle_tool_execution(
    iteration_result: IterationResult,
    session: "SessionEventStream",
    harness_ref: Any,
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
    metrics_deque: deque["ToolExecutionMetrics"],
    autonomous_mode: bool = False,
    ask_user_skip_response: str = "",
) -> tuple[str, dict[str, Any]]:
    """处理工具执行和 Ask User 等待"""
    full_content = iteration_result["full_content"]
    tool_calls = iteration_result["tool_calls"]

    # 无工具调用 = 完成
    if not tool_calls:
        await trigger_hook(hook_registry, HookPoint.RESPONSE_AFTER,
            build_response_after_ctx(session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, False))
        await trigger_hook(hook_registry, HookPoint.SESSION_END,
            build_session_end_ctx(session, harness_ref, "completed", final_response=full_content))
        session.record_session_end("completed")
        return (IterationOutcome.COMPLETED, {"content": full_content})

    # 执行工具调用
    tool_results = await route_tool_calls_with_hooks(
        tool_calls, session, harness_ref, sandbox, hook_registry, metrics_deque)

    # 处理 ask_user 等待
    pending_request = get_pending_ask_user_request()
    if pending_request:
        if autonomous_mode:
            # 自主模式：自动跳过
            logger.info(f"Autonomous mode: skipping ask_user request {pending_request.request_id}")
            clear_ask_user_state()
            session.emit_event(EventType.USER_RESPONSE,
                {"request_id": pending_request.request_id, "responses": [], "cancelled": False,
                 "timeout": False, "autonomous_skip": True, "skip_reason": "autonomous_mode"})
            first_id = tool_calls[0].get("id")
            for r in tool_results:
                if r.get("tool_call_id") == first_id:
                    r["content"] = ask_user_skip_response
            session.emit_event(EventType.TOOL_RESULT, {"tool_call_id": first_id, "content": ask_user_skip_response})
            await trigger_hook(hook_registry, HookPoint.SESSION_RESUME,
                {"reason": "autonomous_skip", "request": pending_request.to_dict()})
            return (IterationOutcome.AUTONOMOUS_SKIP, {})

        # 正常模式：等待用户响应
        session.emit_event(EventType.USER_WAITING,
            {"request": pending_request.to_dict(), "tool_call_id": tool_calls[0].get("id")})
        await trigger_hook(hook_registry, HookPoint.SESSION_PAUSE,
            {"reason": "user_input_required", "request": pending_request.to_dict()})
        return (IterationOutcome.AWAITING_INPUT,
            {"request": pending_request.to_dict(), "tool_call_id": tool_calls[0].get("id")})

    # 发送工具结果
    for result in tool_results:
        session.emit_event(EventType.TOOL_RESULT,
            {"tool_call_id": result["tool_call_id"], "content": result["content"]})

    await trigger_hook(hook_registry, HookPoint.RESPONSE_AFTER,
        build_response_after_ctx(session, harness_ref, {"choices": [{"message": {"content": full_content}}]}, True))

    return (IterationOutcome.CONTINUE, {"tool_results": tool_results})