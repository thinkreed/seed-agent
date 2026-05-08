"""
会话历史 JSONL 列表和搜索功能

提供列出和搜索会话历史的 JSONL fallback 实现。
"""

import os

from ._session_history_jsonl_utils import (
    _ensure_sessions_dir,
    _get_sessions_dir,
    _iter_jsonl_lines,
)


def _list_sessions_jsonl(limit: int = 10) -> str:
    """JSONL fallback implementation - 列出会话

    Args:
        limit: 最大返回数量

    Returns:
        会话列表
    """
    try:
        _ensure_sessions_dir()
        sessions_dir = _get_sessions_dir()
        files = sorted(os.listdir(sessions_dir), reverse=True)
        session_files = [
            f for f in files if f.startswith("session_") and f.endswith(".jsonl")
        ]

        results = []
        for f in session_files[:limit]:
            filepath = os.path.join(sessions_dir, f)
            msg_count = 0
            created_at = "unknown"
            summary = None

            for obj in _iter_jsonl_lines(filepath):
                if obj.get("type") == "session_meta":
                    created_at = obj.get("created_at", "unknown")
                elif obj.get("type") == "message":
                    msg_count += 1
                elif obj.get("type") == "summary":
                    summary = obj.get("content", "")[:100]

            results.append({
                "session_id": f,
                "created_at": created_at,
                "message_count": msg_count,
                "summary": summary,
            })

        if not results:
            return "No sessions found."

        output = "Recent Sessions:\n"
        for s in results:
            output += f"- {s['session_id']}: {s['message_count']} msgs, {s['created_at']}\n"
            if s["summary"]:
                output += f"  Summary: {s['summary']}...\n"

        return output

    except Exception as e:
        return f"Error listing sessions: {e!s}"


def _search_history_jsonl(keyword: str, limit: int = 20) -> str:
    """JSONL fallback implementation - 搜索历史

    Args:
        keyword: 搜索关键词
        limit: 最大返回数量

    Returns:
        匹配的消息上下文
    """
    try:
        _ensure_sessions_dir()
        sessions_dir = _get_sessions_dir()
        files = [
            f
            for f in os.listdir(sessions_dir)
            if f.startswith("session_") and f.endswith(".jsonl")
        ]

        results = []
        keyword_lower = keyword.lower()

        for f in files:
            filepath = os.path.join(sessions_dir, f)
            messages = []

            for obj in _iter_jsonl_lines(filepath):
                if obj.get("type") == "message":
                    messages.append(obj)

            for i, msg in enumerate(messages):
                content = msg.get("content", "")
                if content and keyword_lower in content.lower():
                    context_start = max(0, i - 1)
                    context_end = min(len(messages), i + 2)
                    context = messages[context_start:context_end]

                    results.append({
                        "session_id": f,
                        "timestamp": msg.get("timestamp", "unknown"),
                        "role": msg.get("role"),
                        "matched": content[:300] + "..." if len(content) > 300 else content,
                        "context": [
                            f"{m.get('role')}: {m.get('content', '')[:100]}"
                            for m in context
                        ],
                    })

                    if len(results) >= limit:
                        break

            if len(results) >= limit:
                break

        if not results:
            return f"No matches found for: {keyword}"

        output = f"Found {len(results)} matches for '{keyword}':\n"
        for r in results:
            output += f"\n[{r['session_id']}] {r['timestamp']}\n"
            output += f"{r['role']}: {r['matched']}\n"
            output += f"Context: {r['context']}\n"

        return output

    except Exception as e:
        return f"Error searching history: {e!s}"