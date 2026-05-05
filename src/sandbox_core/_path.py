"""
Sandbox 路径映射模块

处理沙盒路径与主机路径的映射转换。
"""

import fnmatch
import logging
from pathlib import Path
from typing import Any

from src.sandbox_core._types import PATH_KEYS, PermissionAction

logger = logging.getLogger(__name__)


class PathMapper:
    """路径映射器

    处理沙盒内路径与主机路径的映射转换：
    - /workspace/... → {workspace_path}/...
    - /sandbox/... → {fs_root}/...
    """

    def __init__(
        self,
        fs_root: Path,
        workspace_path: Path,
    ):
        self._fs_root = fs_root
        self._workspace_path = workspace_path

    def map_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        """路径映射：沙盒内路径 → 主机路径

        Args:
            args: 工具参数

        Returns:
            映射后的参数
        """
        mapped: dict[str, Any] = {}
        for key, value in args.items():
            if key in PATH_KEYS and isinstance(value, str):
                mapped[key] = self._map_single_path(value)
            elif isinstance(value, dict):
                mapped[key] = self.map_paths(value)
            elif isinstance(value, list):
                mapped[key] = [
                    self._map_single_path(v)
                    if isinstance(v, str) and key in PATH_KEYS
                    else v
                    for v in value
                ]
            else:
                mapped[key] = value

        return mapped

    def _map_single_path(self, path: str) -> str:
        """映射单个路径

        Args:
            path: 原始路径

        Returns:
            映射后的主机路径
        """
        # 沙盒内路径映射
        if path.startswith("/workspace/"):
            mapped = str(self._workspace_path / path[11:])
        elif path.startswith("/sandbox/"):
            mapped = str(self._fs_root / path[9:])
        elif path.startswith("/"):
            # 根路径下的其他目录映射到沙盒
            mapped = str(self._fs_root / path[1:])
        else:
            # 相对路径保持不变
            mapped = path

        logger.debug(f"Path mapped: {path} -> {mapped}")
        return mapped

    def reverse_map_path(self, host_path: str) -> str:
        """反向映射：主机路径 → 沙盒内路径

        Args:
            host_path: 主机路径

        Returns:
            沙盒内路径
        """
        host_path_obj = Path(host_path).resolve()

        # 检查是否在 workspace 目录下
        try:
            rel_to_workspace = host_path_obj.relative_to(self._workspace_path.resolve())
            return f"/workspace/{rel_to_workspace}"
        except ValueError:
            logger.debug(f"Path not in workspace: {host_path_obj}")

        # 检查是否在沙盒目录下
        try:
            rel_to_sandbox = host_path_obj.relative_to(self._fs_root.resolve())
            return f"/sandbox/{rel_to_sandbox}"
        except ValueError:
            logger.debug(f"Path not in sandbox root: {host_path_obj}")

        # 其他路径直接返回
        return host_path


class PermissionChecker:
    """权限检查器"""

    def __init__(
        self,
        permissions: dict[str, Any],
        path_mapper: PathMapper,
    ):
        self._permissions = permissions
        self._path_mapper = path_mapper

    def check_permission(self, tool_name: str, args: dict[str, Any]) -> bool:
        """检查工具执行权限

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            是否允许执行
        """
        # 获取权限配置
        perm = self._permissions.get(tool_name)

        if perm is None:
            # 未配置的工具默认允许（向后兼容）
            logger.debug(
                f"No permission config for tool: {tool_name}, allowing by default"
            )
            return True

        if perm.action == PermissionAction.DENY:
            return False

        # 检查路径模式
        if perm.path_patterns and perm.path_patterns != ["*"]:
            for key in PATH_KEYS:
                if key in args:
                    path = args[key]
                    if not self._match_path_patterns(path, perm.path_patterns):
                        logger.warning(f"Path not allowed: {path}")
                        return False

        return True

    def _match_path_patterns(self, path: str, patterns: list[str]) -> bool:
        """检查路径是否匹配任一模式"""
        return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)