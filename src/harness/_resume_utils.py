"""Harness 恢复执行辅助模块

提取 resume_with_user_response 的辅助函数。

内容:
- handle_user_response - 处理用户响应并注入历史
- check_and_handle_cancel - 检查取消信号
- process_llm_response - 处理 LLM 响应
- handle_tool_calls - 处理工具调用
"""

import logging
from typing import TYPE_CHECKING, Any

from src.session_event_stream import EventType
from src.tools.builtin_tools import clear_ask_user_state, get_pending_ask_user_request

if TYPE_CHECKING:
    from src.abort_signal import AbortSignal
    from src.session_event_stream import SessionEventStream
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)


def handle_user_response(
    response: "AskUserResult",
    session: "SessionEventStream",
    pending_tool_call_id: str | None,
) -> str:
    """处理用户响应并注入历史

    Args:
        response: 用户响应数据
        session: SessionEventStream 实例
        pending_tool_call_id: 等待的工具调用 ID

    Returns:
        工具结果字符串
    """
    clear_ask_user_state()

    session.emit_event(
        EventType.USER_RESPONSE,
        {
            "request_id": response.request_id,
            "responses": [r.to_dict() for r in response.responses],
            "cancelled": response.cancelled,
            "timeout": response.timeout,
        },
    )

    if response.cancelled:
        tool_result = "[USER_CANCELLED]"
    elif response.timeout:
        tool_result = "[USER_TIMEOUT]"
    else:
        selected = response.get_selected_values()
        tool_result = f"User selected: {selected}"

    if pending_tool_call_id:
        session.emit_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": pending_tool_call_id, "content": tool_result},
        )

    return tool_result


def check_and_handle_cancel(
    signal: "AbortSignal | None",
    session: "SessionEventStream",
    iteration: int,
) -> dict[str, Any] | None:
    """检查取消信号并处理

    Args:
        signal: 取消信号
        session: SessionEventStream 实例
        iteration: 当前迭代次数

    Returns:
        如果取消则返回取消结果 dict，否则返回 None
    """
    if signal is None or not signal.aborted:
        return None

    reason = signal.reason if signal else "unknown"
    session.emit_event(
        EventType.EXECUTION_CANCEL,
        {"reason": reason, "iteration": iteration},
    )

    return {
        "status": "cancelled",
        "content": "",
        "pending_request": None,
        "cancel_reason": reason,
        "iterations": iteration,
    }


def process_llm_response(
    resp: dict[str, Any],
    session: "SessionEventStream",
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """处理 LLM 响应

    Args:
        resp: LLM 响应
        session: SessionEventStream 实例

    Returns:
        (文本内容, 消息字典, LLM 数据)
    """
    choices = resp.get("choices", [])
    if not choices:
        logger.warning("LLM response has empty choices")
        return "", {}, {}

    choice = choices[0]
    message = choice.get("message", {})

    llm_data: dict[str, Any] = {}
    if message.get("content"):
        llm_data["content"] = message["content"]
    if message.get("tool_calls"):
        llm_data["tool_calls"] = message["tool_calls"]

    session.emit_event(EventType.LLM_RESPONSE, llm_data)

    return message.get("content", ""), message, llm_data


async def handle_tool_calls_result(
    tool_results: list[dict[str, Any]],
    session: "SessionEventStream",
) -> dict[str, Any] | None:
    """处理工具调用结果

    Args:
        tool_results: 工具执行结果列表
        session: SessionEventStream 实例

    Returns:
        如果触发了 ask_user 等待则返回等待状态 dict，否则返回 None
    """
    pending_request = get_pending_ask_user_request()
    if pending_request:
        session.emit_event(
            EventType.USER_WAITING,
            {"request": pending_request.to_dict()},
        )
        return {"pending_request": pending_request}

    # 记录工具结果事件
    for result in tool_results:
        session.emit_event(
            EventType.TOOL_RESULT,
            {
                "tool_call_id": result["tool_call_id"],
                "content": result["content"],
            },
        )

    return None