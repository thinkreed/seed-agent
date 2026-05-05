"""
Sandbox (工作台) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- Sandbox 是工作台，提供隔离的执行环境
- 隔离的文件系统、进程、网络执行
- 可重建、可销毁、可扩展
- 不存储凭证

重构说明：
- 类型定义移至 sandbox_core/_types.py
- 路径映射移至 sandbox_core/_path.py
- 执行逻辑移至 sandbox_core/_execution.py
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.sandbox_core import (
    DEFAULT_TOOL_NAMES,
    ExecutionResult,
    ISOLATION_LEVELS,
    IsolationLevel,
    PathMapper,
    PermissionAction,
    PermissionChecker,
    SandboxPermission,
    ToolExecutor,
)
from src.tools import ToolRegistry
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


def _get_default_sandbox_root() -> Path:
    """获取默认沙盒根目录（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().sandbox_dir
    except RuntimeError:
        return Path.home() / ".seed" / "sandbox"


class Sandbox:
    """隔离的执行沙盒

    三件套解耦架构中的"工作台"层：
    - 隔离的文件系统访问
    - 隔离的进程执行
    - 路径映射和安全检查
    - 工具注册和执行

    安全特性：
    - 路径映射：沙盒内路径 → 主机路径
    - 权限检查：禁止危险操作
    - 输出截断：防止过大输出
    - 凭证隔离：不存储凭证
    """

    # 类属性（向后兼容）
    ISOLATION_LEVELS = ISOLATION_LEVELS
    PATH_KEYS = [
        "path",
        "file_path",
        "directory",
        "dir",
        "src",
        "dst",
        "source",
        "destination",
        "root",
        "base_path",
        "output_path",
    ]

    # 默认权限配置
    DEFAULT_PERMISSIONS: dict[str, SandboxPermission] = {
        name: SandboxPermission(name, PermissionAction.ALLOW)
        for name in DEFAULT_TOOL_NAMES
    }

    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Path | None = None,
        network_policy: dict[str, Any] | None = None,
        permissions: dict[str, SandboxPermission] | None = None,
        workspace_path: Path | None = None,
    ):
        """初始化 Sandbox

        Args:
            isolation_level: 隔离级别
            file_system_root: 沙盒文件系统根目录
            network_policy: 网络策略 {"allow": [...], "deny": [...]}
            permissions: 权限配置
            workspace_path: 工作目录映射
        """
        self.isolation_level = isolation_level
        self._fs_root = file_system_root or _get_default_sandbox_root()
        self._network_policy = network_policy or {"allow": ["*"], "deny": []}
        self._permissions = permissions or self.DEFAULT_PERMISSIONS.copy()
        self._workspace_path = workspace_path or Path.cwd()

        # 工具注册表
        self._tools: ToolRegistry | None = None

        # 凭证代理
        self._credential_proxy: Any | None = None

        # 核心组件（使用拆分模块）
        self._path_mapper = PathMapper(self._fs_root, self._workspace_path)
        self._permission_checker = PermissionChecker(
            self._permissions, self._path_mapper
        )
        self._tool_executor = ToolExecutor(
            self._tools, self._permissions, self._fs_root, self._workspace_path
        )

        # 确保沙盒目录存在
        os.makedirs(self._fs_root, exist_ok=True)

        logger.info(
            f"Sandbox initialized: isolation={isolation_level.value}, "
            f"fs_root={self._fs_root}, workspace={self._workspace_path}"
        )

    # === 工具管理 ===

    def register_tools(self, tool_registry: ToolRegistry) -> None:
        """注册可用工具"""
        self._tools = tool_registry
        self._tool_executor._tools = tool_registry
        logger.debug(f"Sandbox tools registered: count={len(tool_registry._tools)}")

    def get_tool_schemas(self) -> list[dict]:
        """获取工具 schema"""
        if not self._tools:
            logger.warning("Sandbox has no tools registered")
            return []
        return self._tools.get_schemas()

    def get_registered_tool_names(self) -> list[str]:
        """获取已注册的工具名称列表"""
        if not self._tools:
            return []
        return list(self._tools._tools.keys())

    # === 工具执行 ===

    async def execute_tools(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """在隔离环境中执行工具"""
        results: list[dict[str, Any]] = []

        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)

        return results

    # === 代理方法（向后兼容测试） ===

    def _map_single_path(self, path: str) -> str:
        """映射单个路径（向后兼容）"""
        return self._path_mapper._map_single_path(path)

    def _map_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        """路径映射（向后兼容）"""
        return self._path_mapper.map_paths(args)

    def _check_permission(self, tool_name: str, args: dict[str, Any]) -> bool:
        """权限检查（向后兼容）"""
        return self._permission_checker.check_permission(tool_name, args)

    def _truncate_output(self, output: str, tool_name: str) -> str:
        """输出截断（向后兼容）"""
        return self._tool_executor._truncate_output(output, tool_name)

    async def _execute_single_tool(self, tool_call: dict) -> dict[str, Any]:
        """执行单个工具"""
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        tool_args = parse_tool_arguments(raw_args)
        if is_parse_failed(tool_args):
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": "Error: Failed to parse arguments: invalid JSON",
            }

        # 路径映射
        mapped_args = self._path_mapper.map_paths(tool_args)

        # 权限检查
        if not self._permission_checker.check_permission(tool_name, mapped_args):
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: Permission denied for tool '{tool_name}' in sandbox",
            }

        # 执行
        try:
            result = await self._tool_executor._execute_in_process(tool_name, mapped_args)
            truncated = self._tool_executor._truncate_output(str(result), tool_name)
            return {"tool_call_id": tool_call_id, "role": "tool", "content": truncated}
        except Exception as e:
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: {type(e).__name__}: {str(e)[:500]}",
            }

    # === 路径映射（代理方法） ===

    def reverse_map_path(self, host_path: str) -> str:
        """反向映射：主机路径 → 沙盒内路径"""
        return self._path_mapper.reverse_map_path(host_path)

    # === 状态管理 ===

    def cleanup(self) -> None:
        """清理沙盒状态"""
        logger.info(f"Sandbox cleanup: isolation={self.isolation_level.value}")

    def get_status(self) -> dict[str, Any]:
        """获取沙盒状态"""
        return {
            "isolation_level": self.isolation_level.value,
            "fs_root": str(self._fs_root),
            "workspace_path": str(self._workspace_path),
            "tools_registered": len(self._tools._tools) if self._tools else 0,
            "network_policy": self._network_policy,
            "permissions_count": len(self._permissions),
        }

    # === 权限配置 ===

    def set_permission(
        self,
        tool_name: str,
        action: PermissionAction,
        path_patterns: list[str] | None = None,
        max_output_size: int = 10000,
    ) -> None:
        """设置单个工具权限"""
        self._permissions[tool_name] = SandboxPermission(
            tool_name, action, path_patterns, max_output_size
        )
        self._permission_checker._permissions = self._permissions
        logger.info(f"Permission set: {tool_name} -> {action.value}")

    def get_permissions(self) -> dict[str, Any]:
        """获取所有权限配置"""
        return {
            name: {
                "action": perm.action.value,
                "path_patterns": perm.path_patterns,
                "max_output_size": perm.max_output_size,
            }
            for name, perm in self._permissions.items()
        }

    def deny_all_tools(self) -> None:
        """拒绝所有工具"""
        for name in self._permissions:
            self._permissions[name].action = PermissionAction.DENY
        self._permission_checker._permissions = self._permissions
        logger.info("All tools denied")

    def allow_readonly_tools(self) -> None:
        """只允许只读工具"""
        readonly_tools = [
            "file_read",
            "list_directory",
            "search_memory",
            "load_memory",
            "load_skill",
            "ask_user_question",
            "list_subagents",
            "check_ralph_status",
            "list_scheduled_tasks",
        ]
        for name, perm in self._permissions.items():
            if name in readonly_tools:
                perm.action = PermissionAction.ALLOW
            else:
                perm.action = PermissionAction.DENY
        self._permission_checker._permissions = self._permissions
        logger.info("Readonly mode enabled")

    # === 凭证代理 ===

    def set_credential_proxy(self, proxy: Any) -> None:
        """设置凭证代理"""
        self._credential_proxy = proxy
        logger.info("Credential proxy set")

    def get_credential(self, credential_name: str) -> str | None:
        """通过代理获取凭证"""
        if self._credential_proxy:
            return self._credential_proxy.get_credential(credential_name)
        return None


# 导出类型（向后兼容）
__all__ = [
    "Sandbox",
    "IsolationLevel",
    "PermissionAction",
    "SandboxPermission",
    "ExecutionResult",
]