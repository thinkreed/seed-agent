"""
Ralph State 核心模块

提供 RalphLoop 和 AutonomousExplorer 共享的状态管理逻辑。
"""

from src.ralph_state_core._context import extract_critical_context, reset_context
from src.ralph_state_core._limits import check_safety_limits
from src.ralph_state_core._persistence import (
    cleanup_state_file,
    generate_status_report,
    load_or_init_state,
    persist_state,
)
from src.ralph_state_core._types import RalphState

__all__ = [
    # Types
    "RalphState",
    # Limits
    "check_safety_limits",
    "cleanup_state_file",
    # Context
    "extract_critical_context",
    "generate_status_report",
    "load_or_init_state",
    # Persistence
    "persist_state",
    "reset_context",
]