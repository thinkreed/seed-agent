"""
会话历史 JSONL 加载功能

提供加载会话历史的 JSONL fallback 实现。
"""

from ._session_history_jsonl_utils import (
    _resolve_session_filepath,
    _iter_jsonl_lines,
)


def _load_session_history_jsonl(session_id: str) -> str:
    """JSONL fallback implementation - 加载会话历史

    Args:
        session_id: 会话 ID 或文件名

    Returns:
        会话内容摘要
    """
    try:
        filepath, found = _resolve_session_filepath(session_id)
        if not found:
            return f"Session not found: {session_id}"

        messages = []
        meta = {}
        summary = None

        for obj in _iter_jsonl_lines(filepath):
            if obj.get("type") == "session_meta":
                meta = obj
            elif obj.get("type") == "message":
                messages.append(obj)
            elif obj.get("type") == "summary":
                summary = obj.get("content")

        # 构建输出
        output = f"Session: {meta.get('session_id', session_id)}\n"
        output += f"Created: {meta.get('created_at', 'unknown')}\n"
        output += f"Messages: {len(messages)}\n"
        if summary:
            output += f"Summary: {summary}\n"
        output += "---\n"

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if msg.get("tool_calls"):
                tc_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in msg["tool_calls"]
                ]
                content = f"[Tool Calls: {', '.join(tc_names)}]"
            if msg.get("tool_call_id"):
                content = msg.get("content", "")[:200]
            if len(content) > 500:
                content = content[:500] + "..."
            output += f"{role}: {content}\n"

        return output

    except Exception as e:
        return f"Error loading session: {e!s}"