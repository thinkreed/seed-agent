"""
会话历史 JSONL 辅助函数

提供目录管理和文件名生成的辅助功能。
"""

import os
from datetime import UTC, datetime

from ._memory_write import _get_sessions_dir


def _ensure_sessions_dir() -> None:
    """确保 sessions 目录存在"""
    os.makedirs(_get_sessions_dir(), exist_ok=True)


def _generate_session_filename() -> str:
    """生成会话文件名"""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"session_{timestamp}.jsonl"


def _resolve_session_filepath(session_id: str) -> tuple[str, bool]:
    """解析会话文件路径

    Args:
        session_id: 会话 ID 或文件名

    Returns:
        (文件路径, 是否找到)
    """
    filepath = os.path.join(_get_sessions_dir(), session_id)

    if os.path.exists(filepath):
        return filepath, True

    # 尝试模糊匹配
    sessions_dir = _get_sessions_dir()
    matches = [
        f for f in os.listdir(sessions_dir)
        if f.startswith(session_id) or session_id in f
    ]
    if matches:
        return os.path.join(sessions_dir, matches[0]), True

    return filepath, False


def _iter_jsonl_lines(filepath: str):
    """迭代 JSONL 文件行

    Args:
        filepath: 文件路径

    Yields:
        解析后的 JSON 对象
    """
    import json

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            yield json.loads(line)