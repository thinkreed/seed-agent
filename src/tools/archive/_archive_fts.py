"""
归档 FTS 辅助函数

FTS5 全文搜索相关工具
"""

from typing import Any


def build_event_content_for_fts(events: list[dict[str, Any]]) -> str:
    """构建事件内容文本用于 FTS 索引

    Args:
        events: 事件列表

    Returns:
        用于 FTS 索引的文本内容
    """
    content_parts = []

    for event in events:
        event_type = event.get("type", "")
        event_data = event.get("data", {})

        if event_type == "user_input":
            content_parts.append(event_data.get("content", ""))
        elif event_type == "llm_response":
            content_parts.append(event_data.get("content", "")[:500])
        elif event_type == "tool_result":
            content_parts.append(event_data.get("content", "")[:200])

    return " ".join(content_parts)