"""
Ralph Core 模块

包含 Ralph Loop 的核心类型、完成验证和状态管理逻辑。
"""

from src.ralph_core._types import CompletionType, MAX_ITERATIONS, MAX_DURATION, ITERATION_INTERVAL
from src.ralph_core._completion import CompletionChecker
from src.ralph_core._state import StateManager, SafetyChecker

__all__ = [
    "CompletionType",
    "MAX_ITERATIONS",
    "MAX_DURATION",
    "ITERATION_INTERVAL",
    "CompletionChecker",
    "StateManager",
    "SafetyChecker",
]