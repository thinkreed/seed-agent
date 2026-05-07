"""
Sandbox Core 模块

包含 Sandbox 的核心类型、路径映射和执行逻辑。
"""

from src.sandbox_core._compat import SandboxCompatMixin
from src.sandbox_core._execution import ToolExecutor
from src.sandbox_core._path import PathMapper, PermissionChecker
from src.sandbox_core._types import (
    DEFAULT_TOOL_NAMES,
    ISOLATION_LEVELS,
    PATH_KEYS,
    ExecutionResult,
    IsolationLevel,
    PermissionAction,
    SandboxPermission,
)

__all__ = [
    # 类型
    "IsolationLevel",
    "PermissionAction",
    "SandboxPermission",
    "ExecutionResult",
    "DEFAULT_TOOL_NAMES",
    "ISOLATION_LEVELS",
    "PATH_KEYS",
    # 路径映射
    "PathMapper",
    "PermissionChecker",
    # 执行
    "ToolExecutor",
    # 向后兼容
    "SandboxCompatMixin",
]