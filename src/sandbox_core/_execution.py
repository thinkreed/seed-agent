"""
Sandbox 工具执行模块

处理工具在不同隔离级别下的执行逻辑。
"""

import asyncio
import json
import logging
from contextlib import closing
from typing import Any

from src.sandbox_core._types import ExecutionResult, IsolationLevel, SandboxPermission
from src.tools.utils import is_parse_failed, parse_tool_arguments

logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具执行器

    根据隔离级别执行工具：
    - PROCESS: 进程内执行（通过 ToolRegistry）
    - CONTAINER: Docker 容器执行
    """

    def __init__(
        self,
        tools_registry: Any | None,
        permissions: dict[str, SandboxPermission],
        fs_root: Any,
        workspace_path: Any,
    ):
        self._tools = tools_registry
        self._permissions = permissions
        self._fs_root = fs_root
        self._workspace_path = workspace_path

    async def execute_tools(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """在隔离环境中执行工具

        Args:
            tool_calls: 工具调用列表

        Returns:
            执行结果列表
        """
        results: list[dict[str, Any]] = []

        for tc in tool_calls:
            result = await self._execute_single_tool(tc)
            results.append(result)

        return results

    async def _execute_single_tool(self, tool_call: dict) -> dict[str, Any]:
        """执行单个工具"""
        tool_call_id = tool_call.get("id", "unknown")
        func_data = tool_call.get("function", {})
        tool_name = func_data.get("name", "unknown")
        raw_args = func_data.get("arguments", "{}")

        # 使用统一函数解析参数
        tool_args = parse_tool_arguments(raw_args)
        if is_parse_failed(tool_args):
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": "Error: Failed to parse arguments: invalid JSON",
            }

        # 根据隔离级别执行
        try:
            result = await self._execute_in_process(tool_name, tool_args)

            # 输出截断
            truncated_result = self._truncate_output(str(result), tool_name)

            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": truncated_result,
            }

        except Exception as e:
            logger.exception(f"Tool execution failed: {tool_name}")
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: {type(e).__name__}: {str(e)[:500]}",
            }

    async def _execute_in_process(self, tool_name: str, args: dict[str, Any]) -> Any:
        """进程内执行工具（通过 ToolRegistry）

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

    async def _execute_in_container(self, tool_name: str, args: dict[str, Any]) -> str:
        """Docker 容器级隔离执行

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
            logger.warning(
                f"Docker not installed, falling back to process execution for {tool_name}"
            )
            return await self._execute_in_process(tool_name, args)

        args_json = json.dumps(args)
        cmd = f"python -c 'from src.tools.builtin_tools import {tool_name}; print({tool_name}(**json.loads(\"{args_json}\")))'"

        try:
            with closing(docker.from_env()) as client:
                container = client.containers.run(
                    "seed-agent-sandbox:latest",
                    cmd,
                    volumes={
                        str(self._workspace_path): {"bind": "/workspace", "mode": "rw"},
                        str(self._fs_root): {"bind": "/sandbox", "mode": "rw"},
                    },
                    remove=True,
                    stdout=True,
                    stderr=True,
                )
                return (
                    container.decode() if isinstance(container, bytes) else str(container)
                )
        except Exception as e:
            logger.exception(f"Container execution failed for {tool_name}")
            return await self._execute_in_process(tool_name, args)

    def _truncate_output(self, output: str, tool_name: str) -> str:
        """截断输出以防止过大"""
        perm = self._permissions.get(tool_name)
        max_size = perm.max_output_size if perm else 10000

        if len(output) > max_size:
            truncated = output[:max_size]
            return truncated + f"\n... [truncated, total {len(output)} chars]"
        return output