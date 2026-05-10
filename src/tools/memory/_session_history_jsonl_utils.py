"""
会话历史 JSONL 辅助函数

提供目录管理和文件名生成的辅助功能。
"""

from datetime import UTC, datetime
from pathlib import Path

from ._memory_write import _get_sessions_dir


def _ensure_sessions_dir() -> None:
    """确保 sessions 目录存在"""
    Path(_get_sessions_dir()).mkdir(parents=True, exist_ok=True)


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
    sessions_dir = Path(_get_sessions_dir())
    filepath = sessions_dir / session_id

    if filepath.exists():
        return str(filepath), True

    # 尝试模糊匹配
    matches = [
        f for f in sessions_dir.iterdir()
        if f.name.startswith(session_id) or session_id in f.name
    ]
    if matches:
        return str(matches[0]), True

    return str(filepath), False


def _iter_jsonl_lines(filepath: str):
    """迭代 JSONL 文件行

    Args:
        filepath: 文件路径

    Yields:
        解析后的 JSON 对象
    """
    import json

    path = Path(filepath)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        yield json.loads(line)