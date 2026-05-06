"""Ralph Loop 完成标志工具

提供完成标志写入功能:
- write_completion_marker: 写入完成标志
- _get_completion_promise_file: 获取完成标志文件路径
- _get_ralph_state_dir: 获取 Ralph 状态目录
"""

import logging
from pathlib import Path

from src.ralph_state import _ensure_ralph_dir

logger = logging.getLogger(__name__)


def _get_completion_promise_file() -> Path:
    """获取完成标志文件路径（动态）"""
    return _ensure_ralph_dir().parent / "completion_promise"


def _get_ralph_state_dir() -> Path:
    """获取 Ralph 状态目录（动态）"""
    return _ensure_ralph_dir()


def write_completion_marker(
    content: str = "DONE", marker_path: str | None = None
) -> str:
    """写入完成标志（用于 Ralph Loop 的 marker_file 完成验证）

    当 Agent 完成任务后，调用此工具写入完成标志。
    Ralph Loop 会检测到此标志并退出循环。

    Args:
        content: 标志内容（默认 "DONE"，支持 "COMPLETE", "TASK_FINISHED"）
        marker_path: 标志文件路径（默认 ~/.seed/completion_promise）

    Returns:
        成功消息

    Example:
        write_completion_marker("DONE")  # 使用默认路径
        write_completion_marker("COMPLETE", ".seed/custom_marker")  # 自定义路径
    """
    # 解析路径
    ralph_dir = _get_ralph_state_dir()
    if marker_path:
        path = Path(marker_path)
        if not path.is_absolute():
            path = ralph_dir.parent / marker_path
    else:
        path = _get_completion_promise_file()

    # 确保目录存在并写入标志
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except OSError as e:
        return f"Error: Failed to write completion marker - {type(e).__name__}: {str(e)[:100]}"

    return f"Completion marker written: {path} -> {content}"