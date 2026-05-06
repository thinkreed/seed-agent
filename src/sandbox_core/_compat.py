"""Sandbox 向后兼容方法

提供代理方法，委托给 PathMapper, PermissionChecker, ToolExecutor。
"""

from __future__ import annotations

from typing import Any

from src.sandbox_core._path import PathMapper, PermissionChecker
from src.sandbox_core._execution import ToolExecutor
from src.sandbox_core._types import PermissionAction, SandboxPermission


class SandboxCompatMixin:
    """向后兼容 mixin

    提供旧版 Sandbox API 的代理方法。
    子类需要提供:
    - _path_mapper: PathMapper
    - _permission_checker: PermissionChecker
    - _tool_executor: ToolExecutor
    - _permissions: dict[str, SandboxPermission]
    """

    _path_mapper: PathMapper
    _permission_checker: PermissionChecker
    _tool_executor: ToolExecutor
    _permissions: dict[str, SandboxPermission]

    def _map_single_path(self: Any, path: str) -> str:
        """映射单个路径（向后兼容）"""
        return self._path_mapper._map_single_path(path)

    def _map_paths(self: Any, args: dict[str, Any]) -> dict[str, Any]:
        """路径映射（向后兼容）"""
        return self._path_mapper.map_paths(args)

    def _check_permission(self: Any, tool_name: str, args: dict[str, Any]) -> bool:
        """权限检查（向后兼容）"""
        return self._permission_checker.check_permission(tool_name, args)

    def _truncate_output(self: Any, output: str, tool_name: str) -> str:
        """输出截断（向后兼容）"""
        return self._tool_executor._truncate_output(output, tool_name)


__all__ = ["SandboxCompatMixin"]