"""
凭证隔离沙盒 - 隔离执行模块

负责:
- 容器级隔离执行
- 统一执行入口
- 隔离级别路由
"""

import contextlib
import json
import logging
import os
import tempfile

from src.sandbox import IsolationLevel
from src.security.credential_isolated._environment import (
    create_isolated_environment,
    detect_credential_access_attempt,
)
from src.security.credential_isolated._sanitize import sanitize_output
from src.security.credential_isolated._execution_process import (
    execute_in_isolated_process,
)

logger = logging.getLogger(__name__)


async def execute_in_isolated_container(
    tool_name: str,
    args: dict,
    workspace_path: str,
    fs_root: str,
    isolated_env: dict[str, str],
    enforce_credential_isolation: bool = True,
    timeout: float = 30.0,
) -> str:
    """Docker 容器级隔离执行（无凭证）

    创建临时容器执行，不传递任何环境变量。
    使用临时文件传递参数，避免命令注入风险。

    Args:
        tool_name: 工具名称
        args: 工具参数
        workspace_path: 工作目录
        fs_root: Sandbox 文件系统根目录
        isolated_env: 环境变量（用于降级）
        enforce_credential_isolation: 是否强制凭证隔离
        timeout: 执行超时

    Returns:
        执行结果
    """
    try:
        import docker
    except ImportError:
        logger.warning("Docker not installed, falling back to process isolation")
        return await execute_in_isolated_process(
            tool_name, args, workspace_path, isolated_env,
            enforce_credential_isolation, timeout
        )

    # 检查是否尝试访问凭证
    args_str = json.dumps(args)
    if detect_credential_access_attempt(args_str, enforce=enforce_credential_isolation):
        logger.warning(f"Potential credential access attempt detected in tool: {tool_name}")
        return "[BLOCKED] Credential access attempt detected in sandbox"

    # 白名单验证 tool_name
    if not tool_name.replace("_", "").replace("-", "").isalnum():
        logger.error(f"Invalid tool_name: {tool_name}")
        return f"[BLOCKED] Invalid tool name: {tool_name}"

    # 使用临时文件传递参数
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as args_file:
        json.dump(args, args_file)
        args_file_path = args_file.name

    safe_cmd = f"""
import json
with open('/tmp/args.json') as f:
    args = json.load(f)
from src.tools.builtin_tools import {tool_name}
result = {tool_name}(**args)
print(result)
"""

    from contextlib import closing

    try:
        with closing(docker.from_env()) as client:
            container = client.containers.run(
                "seed-agent-sandbox:latest",
                ["python", "-c", safe_cmd],
                volumes={
                    workspace_path: {"bind": "/workspace", "mode": "rw"},
                    fs_root: {"bind": "/sandbox", "mode": "rw"},
                    args_file_path: {"bind": "/tmp/args.json", "mode": "ro"},
                },
                environment={},  # 不传递任何环境变量（关键）
                remove=True,
                stdout=True,
                stderr=True,
            )

            result = container.decode() if isinstance(container, bytes) else str(container)
            return sanitize_output(result)

    except Exception as e:
        with contextlib.suppress(OSError):
            os.unlink(args_file_path)
        logger.exception(f"Container execution failed: {e}")
        # 降级到进程级隔离
        return await execute_in_isolated_process(
            tool_name, args, workspace_path, isolated_env,
            enforce_credential_isolation, timeout
        )


async def execute_isolated(
    tool_name: str,
    args: dict,
    workspace_path: str,
    fs_root: str,
    isolation_level: IsolationLevel,
    blocked_env_vars: list[str],
    enforce_credential_isolation: bool = True,
    timeout: float = 30.0,
) -> str:
    """统一入口：根据隔离级别执行

    Args:
        tool_name: 工具名称
        args: 工具参数
        workspace_path: 工作目录
        fs_root: Sandbox 文件系统根目录
        isolation_level: 隔离级别
        blocked_env_vars: 屏蔽的环境变量列表
        enforce_credential_isolation: 是否强制凭证隔离
        timeout: 执行超时

    Returns:
        执行结果
    """
    isolated_env = create_isolated_environment(blocked_env_vars)

    if isolation_level == IsolationLevel.CONTAINER:
        return await execute_in_isolated_container(
            tool_name, args, workspace_path, fs_root,
            isolated_env, enforce_credential_isolation, timeout
        )
    else:
        # 默认进程级隔离
        return await execute_in_isolated_process(
            tool_name, args, workspace_path, isolated_env,
            enforce_credential_isolation, timeout
        )