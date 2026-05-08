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

from ._memory_write import _get_sessions_dir
from ._session_history_jsonl_list import _list_sessions_jsonl, _search_history_jsonl
from ._session_history_jsonl_read import _load_session_history_jsonl
from ._session_history_jsonl_utils import (
    _ensure_sessions_dir,
    _generate_session_filename,
)

logger = logging.getLogger(__name__)


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


# API 导出：所有函数从此模块导出以保持 API 兼容
__all__ = [
    "_save_session_history_jsonl",
    "_load_session_history_jsonl",
    "_list_sessions_jsonl",
    "_search_history_jsonl",
]