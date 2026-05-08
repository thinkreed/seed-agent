"""
LLM 摘要格式化函数

提取事件格式化逻辑，支持摘要生成。
"""

from typing import Any


def format_events_for_summary(events: list[dict[str, Any]]) -> str:
    """格式化事件用于摘要生成

    Args:
        events: 事件列表

    Returns:
        格式化的文本
    """
    lines = []

    for event in events:
        event_type = event.get("type", "")
        event_data = event.get("data", {})

        if event_type == "user_input":
            lines.append(f"用户: {event_data.get('content', '')[:200]}")
        elif event_type == "llm_response":
            content = event_data.get("content", "")
            if content:
                lines.append(f"助手: {content[:300]}")
        elif event_type == "tool_call":
            tool_name = event_data.get("function", {}).get("name", "unknown")
            lines.append(f"调用工具: {tool_name}")
        elif event_type == "tool_result":
            lines.append(f"工具结果: {event_data.get('content', '')[:100]}")

    return chr(10).join(lines)


def simple_summary(events: list[dict[str, Any]]) -> str:
    """简单摘要（无 LLM 时使用）

    Args:
        events: 事件列表

    Returns:
        基础摘要
    """
    user_inputs = [e for e in events if e.get("type") == "user_input"]

    if user_inputs:
        first_input = user_inputs[0].get("data", {}).get("content", "")[:100]
        return f"会话包含 {len(events)} 个事件，用户请求: {first_input}"

    return f"会话包含 {len(events)} 个事件"


def simple_findings(events: list[dict[str, Any]]) -> list[str]:
    """简单发现提取（无 LLM 时使用）

    Args:
        events: 事件列表

    Returns:
        发现列表
    """
    findings = []

    # 提取工具调用
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    if tool_events:
        tools_used = set()
        for e in tool_events:
            tool_name = e.get("data", {}).get("function", {}).get("name", "unknown")
            tools_used.add(tool_name)
        findings.append(f"使用了工具: {', '.join(tools_used)}")

    # 提取错误
    error_events = [e for e in events if e.get("type") == "error_occurred"]
    if error_events:
        findings.append(f"发生了 {len(error_events)} 个错误")

    return findings


__all__ = ["format_events_for_summary", "simple_summary", "simple_findings"]