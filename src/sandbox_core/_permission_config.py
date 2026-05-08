"""Sandbox 权限配置模块

处理权限设置、只读模式、拒绝模式等配置逻辑。
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.sandbox_core._types import PermissionAction, SandboxPermission

logger = logging.getLogger(__name__)

# 只读工具列表
READONLY_TOOLS = frozenset([
    "file_read",
    "list_directory",
    "search_memory",
    "load_memory",
    "load_skill",
    "ask_user_question",
    "list_subagents",
    "check_ralph_status",
    "list_scheduled_tasks",
])


class PermissionConfigMixin:
    """权限配置 mixin

    提供权限设置、只读模式、拒绝模式等方法。
    子类需要提供:
    - _permissions: dict[str, SandboxPermission]
    - _permission_checker: PermissionChecker
    """

    _permissions: dict[str, Any]
    _permission_checker: Any

    def set_permission(
        self: Any,
        tool_name: str,
        action: Any,  # PermissionAction
        path_patterns: list[str] | None = None,
        max_output_size: int = 10000,
    ) -> None:
        """设置单个工具权限

        Args:
            tool_name: 工具名称
            action: 权限动作 (ALLOW/DENY/READONLY)
            path_patterns: 允许的路径模式列表
            max_output_size: 最大输出大小限制
        """
        from src.sandbox_core._types import SandboxPermission

        self._permissions[tool_name] = SandboxPermission(
            tool_name, action, path_patterns, max_output_size
        )
        self._permission_checker._permissions = self._permissions
        logger.info(f"Permission set: {tool_name} -> {action.value}")

    def get_permissions(self: Any) -> dict[str, Any]:
        """获取所有权限配置

        Returns:
            权限配置字典
        """
        return {
            name: {
                "action": perm.action.value,
                "path_patterns": perm.path_patterns,
                "max_output_size": perm.max_output_size,
            }
            for name, perm in self._permissions.items()
        }

    def deny_all_tools(self: Any) -> None:
        """拒绝所有工具"""
        from src.sandbox_core._types import PermissionAction

        for name in self._permissions:
            self._permissions[name].action = PermissionAction.DENY
        self._permission_checker._permissions = self._permissions
        logger.info("All tools denied")

    def allow_readonly_tools(self: Any) -> None:
        """只允许只读工具"""
        from src.sandbox_core._types import PermissionAction

        for name, perm in self._permissions.items():
            if name in READONLY_TOOLS:
                perm.action = PermissionAction.ALLOW
            else:
                perm.action = PermissionAction.DENY
        self._permission_checker._permissions = self._permissions
        logger.info("Readonly mode enabled")


__all__ = ["PermissionConfigMixin", "READONLY_TOOLS"]