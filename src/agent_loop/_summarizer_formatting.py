"""
Summarizer 事件格式化

提取 format_events_for_summary 方法。
"""

from src.session_event_stream import EventType


def format_events_for_summary(events: list[dict]) -> str:
    """将事件格式化为摘要文本

    Args:
        events: 事件列表

    Returns:
        格式化的摘要文本
    """
    lines = []
    for event in events:
        event_type = event["type"]
        data = event["data"]

        if event_type == EventType.USER_INPUT.value:
            lines.append(f"user: {data.get('content', '')}")
        elif event_type == EventType.LLM_RESPONSE.value:
            content = data.get("content", "")
            if data.get("tool_calls"):
                tc_names = [
                    tc["function"]["name"]
                    for tc in data["tool_calls"]
                    if tc.get("function")
                ]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if content:
                lines.append(f"assistant: {content}")
        elif event_type == EventType.TOOL_RESULT.value:
            content = data.get("content", "")[:200]
            lines.append(f"tool: {content}")

    return "\n".join(lines)


__all__ = ["format_events_for_summary"]