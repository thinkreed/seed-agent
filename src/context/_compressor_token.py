"""
上下文压缩 Token 估算模块

包含 Token 估算、事件转换、历史构建
"""

from typing import Any

from src.session_event_stream import EventType


def estimate_tokens(messages: list[dict[str, Any]], token_per_char: float) -> int:
    """估算 Token 数"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += int(len(content) * token_per_char)

        if msg.get("tool_calls"):
            tc_str = str(msg["tool_calls"])
            total += int(len(tc_str) * token_per_char)

    return total


def event_to_message(event: dict[str, Any]) -> dict[str, Any] | None:
    """将事件转换为消息格式"""
    event_type = event["type"]
    data = event["data"]

    if event_type == EventType.USER_INPUT.value:
        return {"role": "user", "content": data.get("content", "")}

    if event_type == EventType.LLM_RESPONSE.value:
        msg: dict[str, Any] = {"role": "assistant"}
        content = data.get("content")
        if content:
            msg["content"] = content
        if data.get("tool_calls"):
            msg["tool_calls"] = data["tool_calls"]
        return msg

    if event_type == EventType.TOOL_RESULT.value:
        return {
            "role": "tool",
            "tool_call_id": data.get("tool_call_id"),
            "content": data.get("content", ""),
        }

    return None


def build_history_from_session(
    session: Any,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """从 Session 构建完整历史（包括摘要）"""
    messages: list[dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    last_summary = session.find_last_summary_marker()

    if last_summary:
        summary_content = last_summary["data"].get("summary", "")
        if summary_content:
            messages.append(
                {"role": "user", "content": f"[历史摘要]\n{summary_content}"}
            )

    recent_events = session.get_events_since_last_summary(
        [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
    )

    for event in recent_events:
        msg = event_to_message(event)
        if msg:
            messages.append(msg)

    return messages