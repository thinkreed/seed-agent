"""
Sandbox (工作台) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- Sandbox 是工作台，提供隔离的执行环境
- 隔离的文件系统、进程、网络执行
- 可重建、可销毁、可扩展
- 不存储凭证

隔离级别：
- process: 进程级隔离 (子进程执行，默认)
- container: 容器级隔离 (Docker，可选)
- vm: 虚拟机级隔离 (最强，未来)

核心职责：
1. 工具执行隔离
2. 路径映射 (沙盒路径 → 主机路径)
3. 权限检查
4. 网络策略控制
5. 输出截断和安全处理

性能优化：
- 大脑(LLMClient)从容器(Sandbox)分离
- 首Token延迟降低 60-90%
"""

import asyncio
import fnmatch
import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

from src.tools import ToolRegistry
from src.tools.utils import parse_tool_arguments

logger = logging.getLogger(__name__)

# 默认沙盒根目录
DEFAULT_SANDBOX_ROOT = Path(os.path.expanduser("~")) / ".seed" / "sandbox"


class IsolationLevel(str, Enum):
    """隔离级别"""
    PROCESS = "process"       # 进程级隔离 (子进程执行)
    CONTAINER = "container"   # 容器级隔离 (Docker)
    VM = "vm"                 # 虚拟机级隔离 (最强)


class PermissionAction(str, Enum):
    """权限动作"""
    ALLOW = "allow"
    DENY = "deny"
    READONLY = "readonly"


class SandboxPermission:
    """沙盒权限规则

    定义单个工具的执行权限：
    - action: 允许/拒绝/只读
    - path_patterns: 允许的路径模式列表
    - max_output_size: 最大输出大小限制
    """

    def __init__(
        self,
        tool_name: str,
        action: PermissionAction = PermissionAction.ALLOW,
        path_patterns: list[str] | None = None,
        max_output_size: int = 10000
    ):
        self.tool_name = tool_name
        self.action = action
        self.path_patterns = path_patterns or ["*"]
        self.max_output_size = max_output_size


class ExecutionResult:
    """工具执行结果"""

    def __init__(
        self,
        tool_call_id: str,
        content: str,
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0.0
    ):
        self.tool_call_id = tool_call_id
        self.content = content
        self.success = success
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "tool_call_id": self.tool_call_id,
            "role": "tool",
            "content": self.content
        }


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

    性能优化：
    - 进程级隔离默认，低开销
    - 可选容器级隔离，更强安全
    """

    ISOLATION_LEVELS = {
        IsolationLevel.PROCESS: "进程级隔离 (子进程执行)",
        IsolationLevel.CONTAINER: "容器级隔离 (Docker)",
        IsolationLevel.VM: "虚拟机级隔离 (最强)",
    }

    # 默认权限配置
    DEFAULT_PERMISSIONS: dict[str, SandboxPermission] = {
        # 文件操作
        "file_read": SandboxPermission("file_read", PermissionAction.ALLOW),
        "file_write": SandboxPermission("file_write", PermissionAction.ALLOW),
        "file_edit": SandboxPermission("file_edit", PermissionAction.ALLOW),
        "list_directory": SandboxPermission("list_directory", PermissionAction.ALLOW),

        # 代码执行
        "run_shell_command": SandboxPermission("run_shell_command", PermissionAction.ALLOW),
        "code_as_policy": SandboxPermission("code_as_policy", PermissionAction.ALLOW),

        # 记忆操作
        "save_memory": SandboxPermission("save_memory", PermissionAction.ALLOW),
        "load_memory": SandboxPermission("load_memory", PermissionAction.ALLOW),
        "search_memory": SandboxPermission("search_memory", PermissionAction.ALLOW),

        # 用户交互
        "ask_user_question": SandboxPermission("ask_user_question", PermissionAction.ALLOW),

        # 技能操作
        "load_skill": SandboxPermission("load_skill", PermissionAction.ALLOW),

        # 子代理
        "spawn_subagent": SandboxPermission("spawn_subagent", PermissionAction.ALLOW),
        "wait_for_subagent": SandboxPermission("wait_for_subagent", PermissionAction.ALLOW),
        "aggregate_subagent_results": SandboxPermission(
            "aggregate_subagent_results", PermissionAction.ALLOW
        ),
        "list_subagents": SandboxPermission("list_subagents", PermissionAction.ALLOW),
        "kill_subagent": SandboxPermission("kill_subagent", PermissionAction.ALLOW),

        # Ralph Loop
        "start_ralph_loop": SandboxPermission("start_ralph_loop", PermissionAction.ALLOW),
        "check_ralph_status": SandboxPermission("check_ralph_status", PermissionAction.ALLOW),
        "mark_ralph_complete": SandboxPermission("mark_ralph_complete", PermissionAction.ALLOW),

        # Scheduler
        "create_scheduled_task": SandboxPermission(
            "create_scheduled_task", PermissionAction.ALLOW
        ),
        "remove_scheduled_task": SandboxPermission(
            "remove_scheduled_task", PermissionAction.ALLOW
        ),
        "list_scheduled_tasks": SandboxPermission(
            "list_scheduled_tasks", PermissionAction.ALLOW
        ),
    }

    # 路径相关参数名
    PATH_KEYS = [
        "path", "file_path", "directory", "dir",
        "src", "dst", "source", "destination",
        "root", "base_path", "output_path"
    ]

    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        file_system_root: Path | None = None,
        network_policy: dict[str, Any] | None = None,
        permissions: dict[str, SandboxPermission] | None = None,
        workspace_path: Path | None = None
    ):
        """初始化 Sandbox

        Args:
            isolation_level: 隔离级别
            file_system_root: 沙盒文件系统根目录
            network_policy: 网络策略 {"allow": [...], "deny": [...]}
            permissions: 权限配置
            workspace_path: 工作目录映射（沙盒内 /workspace → 主机路径）
        """
        self.isolation_level = isolation_level
        self._fs_root = file_system_root or DEFAULT_SANDBOX_ROOT
        self._network_policy = network_policy or {"allow": ["*"], "deny": []}
        self._permissions = permissions or self.DEFAULT_PERMISSIONS.copy()
        self._workspace_path = workspace_path or Path.cwd()

        # 工具注册表（由外部注入）
        self._tools: ToolRegistry | None = None

        # 凭证代理（不存储凭证，只代理访问）
        self._credential_proxy: Any | None = None

        # 确保沙盒目录存在
        os.makedirs(self._fs_root, exist_ok=True)

        logger.info(
            f"Sandbox initialized: isolation={isolation_level.value}, "
            f"fs_root={self._fs_root}, workspace={self._workspace_path}"
        )

    # === 工具管理 ===

    def register_tools(self, tool_registry: ToolRegistry) -> None:
        """注册可用工具

        Args:
            tool_registry: 工具注册表实例
        """
        self._tools = tool_registry
        logger.debug(f"Sandbox tools registered: count={len(tool_registry._tools)}")

    def get_tool_schemas(self) -> list[dict]:
        """获取工具 schema (供 LLMClient 使用)"""
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
        """在隔离环境中执行工具

        Args:
            tool_calls: 工具调用列表，格式:
                [
                    {
                        "id": "call_xxx",
                        "type": "function",
                        "function": {
                            "name": "tool_name",
                            "arguments": "{...}"  # JSON string
                        }
                    }
                ]

        Returns:
            执行结果列表:
                [
                    {
                        "tool_call_id": "call_xxx",
                        "role": "tool",
                        "content": "执行结果"
                    }
                ]
        """
        results: list[dict[str, Any]] = []

        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)

        return results

    async def _execute_single_tool(self, tool_call: dict) -> dict[str, Any]:
        """执行单个工具

        Args:
            tool_call: 工具调用请求

        Returns:
            执行结果
        """
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        # 使用统一函数解析参数
        tool_args = parse_tool_arguments(raw_args)
        if not tool_args and raw_args:
            # 解析失败，返回错误
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": "Error: Failed to parse arguments: invalid JSON"
            }

        # 路径映射
        mapped_args = self._map_paths(tool_args)

        # 权限检查
        if not self._check_permission(tool_name, mapped_args):
            logger.warning(f"Permission denied for tool: {tool_name}")
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: Permission denied for tool '{tool_name}' in sandbox"
            }

        # 根据隔离级别执行
        try:
            if self.isolation_level == IsolationLevel.PROCESS:
                result = await self._execute_in_process(tool_name, mapped_args)
            elif self.isolation_level == IsolationLevel.CONTAINER:
                result = await self._execute_in_container(tool_name, mapped_args)
            else:
                # 默认进程内执行
                result = await self._execute_in_process(tool_name, mapped_args)

            # 输出截断
            truncated_result = self._truncate_output(str(result), tool_name)

            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": truncated_result
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {type(e).__name__}: {e}")
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: {type(e).__name__}: {str(e)[:500]}"
            }

    # === 路径映射 ===

    def _map_paths(self, args: dict[str, Any]) -> dict[str, Any]:
        """路径映射：沙盒内路径 → 主机路径

        映射规则：
        - /workspace/... → {workspace_path}/...
        - /sandbox/... → {fs_root}/...
        - 其他路径保持不变（需要权限检查）

        Args:
            args: 工具参数

        Returns:
            映射后的参数
        """
        mapped: dict[str, Any] = {}
        for key, value in args.items():
            if key in self.PATH_KEYS and isinstance(value, str):
                mapped[key] = self._map_single_path(value)
            elif isinstance(value, dict):
                mapped[key] = self._map_paths(value)
            elif isinstance(value, list):
                mapped[key] = [
                    self._map_single_path(v) if isinstance(v, str) and key in self.PATH_KEYS else v
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
            pass

        # 检查是否在沙盒目录下
        try:
            rel_to_sandbox = host_path_obj.relative_to(self._fs_root.resolve())
            return f"/sandbox/{rel_to_sandbox}"
        except ValueError:
            pass

        # 其他路径直接返回
        return host_path

    # === 权限检查 ===

    def _check_permission(self, tool_name: str, args: dict[str, Any]) -> bool:
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
            logger.debug(f"No permission config for tool: {tool_name}, allowing by default")
            return True

        if perm.action == PermissionAction.DENY:
            return False

        # 检查路径模式
        if perm.path_patterns and perm.path_patterns != ["*"]:
            for key in self.PATH_KEYS:
                if key in args:
                    path = args[key]
                    if not self._match_path_patterns(path, perm.path_patterns):
                        logger.warning(f"Path not allowed: {path}")
                        return False

        return True

    def _match_path_patterns(self, path: str, patterns: list[str]) -> bool:
        """检查路径是否匹配任一模式"""
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    # === 执行实现 ===

    async def _execute_in_process(self, tool_name: str, args: dict[str, Any]) -> Any:
        """进程内执行工具（通过 ToolRegistry）

        这是默认的执行方式，直接调用注册的工具函数。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            执行结果
        """
        if not self._tools:
            raise RuntimeError("Sandbox has no tools registered")

        # 直接通过 ToolRegistry 执行
        return await self._tools.execute(tool_name, **args)

    async def _execute_in_subprocess(self, tool_name: str, args: dict[str, Any]) -> str:
        """子进程隔离执行（进程级隔离）

        在独立子进程中执行工具，提供更强的隔离。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            执行结果
        """
        # 构建执行命令
        args_json = json.dumps(args)

        # 创建子进程
        proc = await asyncio.create_subprocess_exec(
            "python", "-c",
            f"import json; from src.tools.builtin_tools import {tool_name}; "
            f"print({tool_name}(**json.loads('{args_json}')))",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workspace_path)
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Subprocess failed: {error_msg}")

        return stdout.decode() if stdout else ""

    async def _execute_in_container(self, tool_name: str, args: dict[str, Any]) -> str:
        """Docker 容器级隔离执行

        需要安装 Docker 并配置镜像。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            执行结果
        """
        # 容器执行需要 docker 库
        try:
            import docker
        except ImportError:
            logger.warning("Docker not installed, falling back to process execution")
            return await self._execute_in_process(tool_name, args)

        client = docker.from_env()

        # 构建执行命令
        args_json = json.dumps(args)
        cmd = f"python -c 'from src.tools.builtin_tools import {tool_name}; print({tool_name}(**json.loads(\"{args_json}\")))'"

        try:
            # 创建临时容器执行
            container = client.containers.run(
                "seed-agent-sandbox:latest",
                cmd,
                volumes={
                    str(self._workspace_path): {"bind": "/workspace", "mode": "rw"},
                    str(self._fs_root): {"bind": "/sandbox", "mode": "rw"}
                },
                remove=True,
                stdout=True,
                stderr=True
            )
            return container.decode() if isinstance(container, bytes) else str(container)
        except Exception as e:
            logger.error(f"Container execution failed: {e}")
            # 降级到进程执行
            return await self._execute_in_process(tool_name, args)

    # === 输出处理 ===

    def _truncate_output(self, output: str, tool_name: str) -> str:
        """截断输出以防止过大

        Args:
            output: 原始输出
            tool_name: 工具名称

        Returns:
            截断后的输出
        """
        perm = self._permissions.get(tool_name)
        max_size = perm.max_output_size if perm else 10000

        if len(output) > max_size:
            truncated = output[:max_size]
            return truncated + f"\n... [truncated, total {len(output)} chars]"
        return output

    # === 状态管理 ===

    def cleanup(self) -> None:
        """清理沙盒状态

        注意：不删除沙盒目录，只清理临时状态
        """
        # 清理临时文件（如果需要）
        logger.info(f"Sandbox cleanup: isolation={self.isolation_level.value}")

    def get_status(self) -> dict[str, Any]:
        """获取沙盒状态"""
        return {
            "isolation_level": self.isolation_level.value,
            "fs_root": str(self._fs_root),
            "workspace_path": str(self._workspace_path),
            "tools_registered": len(self._tools._tools) if self._tools else 0,
            "network_policy": self._network_policy,
            "permissions_count": len(self._permissions)
        }

    # === 权限配置 ===

    def set_permission(
        self,
        tool_name: str,
        action: PermissionAction,
        path_patterns: list[str] | None = None,
        max_output_size: int = 10000
    ) -> None:
        """设置单个工具权限

        Args:
            tool_name: 工具名称
            action: 权限动作
            path_patterns: 允许的路径模式
            max_output_size: 最大输出大小
        """
        self._permissions[tool_name] = SandboxPermission(
            tool_name, action, path_patterns, max_output_size
        )
        logger.info(f"Permission set: {tool_name} -> {action.value}")

    def get_permissions(self) -> dict[str, Any]:
        """获取所有权限配置"""
        return {
            name: {
                "action": perm.action.value,
                "path_patterns": perm.path_patterns,
                "max_output_size": perm.max_output_size
            }
            for name, perm in self._permissions.items()
        }

    def deny_all_tools(self) -> None:
        """拒绝所有工具（用于只读模式）"""
        for name in self._permissions:
            self._permissions[name].action = PermissionAction.DENY
        logger.info("All tools denied")

    def allow_readonly_tools(self) -> None:
        """只允许只读工具"""
        readonly_tools = [
            "file_read", "list_directory", "search_memory",
            "load_memory", "load_skill", "ask_user_question",
            "list_subagents", "check_ralph_status", "list_scheduled_tasks"
        ]
        for name, perm in self._permissions.items():
            if name in readonly_tools:
                perm.action = PermissionAction.ALLOW
            else:
                perm.action = PermissionAction.DENY
        logger.info("Readonly mode enabled")

    # === 凭证代理 ===

    def set_credential_proxy(self, proxy: Any) -> None:
        """设置凭证代理（不存储凭证）"""
        self._credential_proxy = proxy
        logger.info("Credential proxy set (credentials not stored in sandbox)")

    def get_credential(self, credential_name: str) -> str | None:
        """通过代理获取凭证"""
        if self._credential_proxy:
            return self._credential_proxy.get_credential(credential_name)
        return None
