"""Harness 工具调用处理

包含工具调用路由、Ask User 处理、结果记录等逻辑。
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint
from src.session_event_stream import EventType
from src.tools.builtin_tools import clear_ask_user_state, get_pending_ask_user_request

from ._lifecycle_hooks import (
    build_response_after_ctx,
    trigger_hook,
)
from ._metrics import ToolExecutionMetrics
from ._tool_router import route_tool_calls_with_hooks

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def handle_tool_calls(
    message: dict,
    session: "SessionEventStream",
    sandbox: "Sandbox",
    hook_registry: "LifecycleHookRegistry | None",
    harness_ref: Any,
    metrics_deque: deque[ToolExecutionMetrics],
    autonomous_mode: bool,
    ask_user_skip_response: str,
    response: dict,
) -> dict[str, Any]:
    """处理工具调用

    Returns:
        处理结果字典
    """
    tool_calls = message.get("tool_calls", [])
    if not tool_calls:
        return {
            "status": "no_tools",
            "tool_results": None,
        }

    tool_results = await route_tool_calls_with_hooks(
        tool_calls, session, harness_ref, sandbox, hook_registry, metrics_deque
    )

    pending_request = get_pending_ask_user_request()
    if pending_request:
        if autonomous_mode:
            return await _handle_autonomous_skip(
                session, hook_registry, tool_results, tool_calls, ask_user_skip_response
            )

        return await _handle_user_waiting(session, hook_registry, pending_request, tool_results)

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
        "tool_results": tool_results,
        "continue_loop": True,
    }


async def _handle_autonomous_skip(
    session: "SessionEventStream",
    hook_registry: "LifecycleHookRegistry | None",
    tool_results: list,
    tool_calls: list,
    ask_user_skip_response: str,
) -> dict[str, Any]:
    """处理自主模式跳过"""
    logger.info("Autonomous mode: skipping ask_user request")
    clear_ask_user_state()

    pending_request = get_pending_ask_user_request()
    if pending_request:
        session.emit_event(
            EventType.USER_RESPONSE,
            {"request_id": pending_request.request_id, "autonomous_skip": True},
        )

    first_tool_call_id = tool_calls[0].get("id")
    for result in tool_results:
        if result.get("tool_call_id") == first_tool_call_id:
            result["content"] = ask_user_skip_response

    await trigger_hook(hook_registry, HookPoint.SESSION_RESUME, {"reason": "autonomous_skip"})

    return {
        "status": "continue",
        "tool_results": tool_results,
        "continue_loop": True,
        "pending_request": None,
    }


async def _handle_user_waiting(
    session: "SessionEventStream",
    hook_registry: "LifecycleHookRegistry | None",
    pending_request: Any,
    tool_results: list,
) -> dict[str, Any]:
    """处理等待用户输入"""
    session.emit_event(EventType.USER_WAITING, {"request": pending_request.to_dict()})
    await trigger_hook(
        hook_registry,
        HookPoint.SESSION_PAUSE,
        {"reason": "user_input_required", "request": pending_request.to_dict()},
    )

    return {
        "status": "waiting_for_user",
        "tool_results": tool_results,
        "continue_loop": False,
        "pending_request": pending_request.to_dict(),
    }