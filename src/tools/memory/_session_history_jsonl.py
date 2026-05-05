"""
会话历史 JSONL Fallback 实现

当 SQLite session_db.py 不可用时，使用 JSONL 文件存储会话历史。

核心功能：
- _save_session_history_jsonl: 保存会话到 JSONL
- _load_session_history_jsonl: 加载会话历史
- _list_sessions_jsonl: 列出会话
- _search_history_jsonl: 搜索历史

注意：这是 fallback 实现，优先使用 SQLite+FTS5 后端。
"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from ._memory_write import _get_sessions_dir

logger = logging.getLogger(__name__)


def _ensure_sessions_dir() -> None:
    """确保 sessions 目录存在"""
    os.makedirs(_get_sessions_dir(), exist_ok=True)


def _generate_session_filename() -> str:
    """生成会话文件名"""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"session_{timestamp}.jsonl"


def _save_session_history_jsonl(
    messages: list, summary: str | None = None, session_id: str | None = None
) -> str:
    """JSONL fallback implementation - 保存会话历史

    Args:
        messages: 消息列表
        summary: 会话摘要
        session_id: 会话 ID（可选，自动生成）

    Returns:
        状态信息
    """
    try:
        _ensure_sessions_dir()
        if not session_id:
            session_id = _generate_session_filename()

        filepath = os.path.join(_get_sessions_dir(), session_id)

        with open(filepath, "a", encoding="utf-8") as f:
            # 写入元数据
            if not os.path.exists(filepath) or os.stat(filepath).st_size == 0:
                meta = {
                    "type": "session_meta",
                    "session_id": session_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

            # 写入消息
            for msg in messages:
                msg["timestamp"] = datetime.now(UTC).isoformat()
                msg["type"] = "message"
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            # 写入摘要
            if summary:
                summary_line = {
                    "type": "summary",
                    "content": summary,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                f.write(json.dumps(summary_line, ensure_ascii=False) + "\n")

        msg_count = len(messages)
        return f"Session saved: {session_id} ({msg_count} messages)"

    except Exception as e:
        return f"Error saving session: {e!s}"


def _load_session_history_jsonl(session_id: str) -> str:
    """JSONL fallback implementation - 加载会话历史

    Args:
        session_id: 会话 ID 或文件名

    Returns:
        会话内容摘要
    """
    try:
        filepath = os.path.join(_get_sessions_dir(), session_id)
        sessions_dir = _get_sessions_dir()

        # 尝试查找文件
        if not os.path.exists(filepath):
            matches = [
                f
                for f in os.listdir(sessions_dir)
                if f.startswith(session_id) or session_id in f
            ]
            if matches:
                filepath = os.path.join(sessions_dir, matches[0])
            else:
                return f"Session not found: {session_id}"

        messages = []
        meta = {}
        summary = None

        with open(filepath, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
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

            with open(filepath, encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
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

            with open(filepath, encoding="utf-8") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
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