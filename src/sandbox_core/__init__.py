"""
Sandbox Core 模块

包含 Sandbox 的核心类型、路径映射、执行逻辑和配置。
"""

from src.sandbox_core._compat import SandboxCompatMixin
from src.sandbox_core._credential import CredentialProxyMixin
from src.sandbox_core._execution import ToolExecutor
from src.sandbox_core._path import PathMapper, PermissionChecker
from src.sandbox_core._permission_config import PermissionConfigMixin, READONLY_TOOLS
from src.sandbox_core._tool_execution import ToolExecutionMixin
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
    "DEFAULT_TOOL_NAMES",
    "ISOLATION_LEVELS",
    "PATH_KEYS",
    "READONLY_TOOLS",
    "ExecutionResult",
    # 类型
    "IsolationLevel",
    # 路径映射
    "PathMapper",
    "PermissionAction",
    "PermissionChecker",
    # 向后兼容
    "SandboxCompatMixin",
    "SandboxPermission",
    # 执行
    "ToolExecutor",
    # 配置 mixin
    "PermissionConfigMixin",
    "CredentialProxyMixin",
    "ToolExecutionMixin",
]