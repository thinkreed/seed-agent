"""
Ralph Loop 共享状态管理模块（聚合层）

提供 RalphLoop 和 AutonomousExplorer 共享的状态管理逻辑:
- 安全上限检查 (迭代/时间双重保护)
- 状态持久化 (JSON 文件存储)
- 上下文重置 (防止漂移)
- 关键信息提取

路径从 PathsConfig 动态获取。
"""

from pathlib import Path

from src.ralph_state_core import (
    RalphState,
    check_safety_limits,
    cleanup_state_file,
    extract_critical_context,
    generate_status_report,
    load_or_init_state,
    persist_state,
    reset_context,
)
from src.shared_config import get_ralph_dir_with_fallback

# 默认状态目录（延迟获取）
RALPH_STATE_DIR: Path | None = None


def _ensure_ralph_dir() -> Path:
    """确保 Ralph 状态目录已初始化"""
    global RALPH_STATE_DIR
    if RALPH_STATE_DIR is None:
        RALPH_STATE_DIR = get_ralph_dir_with_fallback()
    return RALPH_STATE_DIR


# 导出所有公共 API（向后兼容）
__all__ = [
    # Types
    "RalphState",
    # Limits
    "check_safety_limits",
    # Persistence
    "persist_state",
    "load_or_init_state",
    "cleanup_state_file",
    "generate_status_report",
    # Context
    "extract_critical_context",
    "reset_context",
    # Legacy
    "RALPH_STATE_DIR",
    "_ensure_ralph_dir",
]