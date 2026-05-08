"""Sandbox (工作台) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- Sandbox 是工作台，提供隔离的执行环境
- 隔离的文件系统、进程、网络执行
- 可重建、可销毁、可扩展
- 不存储凭证

重构说明：
- 类型定义: sandbox_core/_types.py
- 路径映射: sandbox_core/_path.py
- 执行逻辑: sandbox_core/_execution.py
- 权限配置: sandbox_core/_permission_config.py
- 凭证代理: sandbox_core/_credential.py
- 向后兼容: sandbox_core/_compat.py
"""

import logging
import os
from pathlib import Path
from typing import Any

from src.sandbox_core import (
    DEFAULT_TOOL_NAMES,
    ISOLATION_LEVELS,
    CredentialProxyMixin,
    ExecutionResult,
    IsolationLevel,
    PathMapper,
    PermissionAction,
    PermissionChecker,
    PermissionConfigMixin,
    SandboxCompatMixin,
    SandboxPermission,
    ToolExecutionMixin,
    ToolExecutor,
)
from src.tools import ToolRegistry

logger = logging.getLogger(__name__)


def _get_default_sandbox_root() -> Path:
    """获取默认沙盒根目录（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().sandbox_dir
    except RuntimeError:
        return Path.home() / ".seed" / "sandbox"


class Sandbox(
    SandboxCompatMixin, PermissionConfigMixin, CredentialProxyMixin, ToolExecutionMixin
):
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
        self.isolation_level = isolation_level
        self._fs_root = file_system_root or _get_default_sandbox_root()
        self._network_policy = network_policy or {"allow": ["*"], "deny": []}
        self._permissions = permissions or self.DEFAULT_PERMISSIONS.copy()
        self._workspace_path = workspace_path or Path.cwd()

        self._tools: ToolRegistry | None = None
        self._credential_proxy: Any | None = None

        # 核心组件
        self._path_mapper = PathMapper(self._fs_root, self._workspace_path)
        self._permission_checker = PermissionChecker(
            self._permissions, self._path_mapper
        )
        self._tool_executor = ToolExecutor(
            self._tools, self._permissions, self._fs_root, self._workspace_path
        )

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
        """在隔离环境中执行工具（委托给 mixin）"""
        return await self.execute_tools_proxy(tool_calls)

    # === 路径映射 ===

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


__all__ = [
    "ExecutionResult",
    "IsolationLevel",
    "PermissionAction",
    "Sandbox",
    "SandboxPermission",
]