"""
Ralph Core 模块

包含 Ralph Loop 的核心类型、完成验证和状态管理逻辑。
"""

from src.ralph_core._completion import CompletionChecker
from src.ralph_core._state import SafetyChecker, StateManager
from src.ralph_core._types import (
    ITERATION_INTERVAL,
    MAX_DURATION,
    MAX_ITERATIONS,
    CompletionType,
)

__all__ = [
    "ITERATION_INTERVAL",
    "MAX_DURATION",
    "MAX_ITERATIONS",
    "CompletionChecker",
    "CompletionType",
    "SafetyChecker",
    "StateManager",
]