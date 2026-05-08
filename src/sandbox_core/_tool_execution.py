"""Sandbox 工具执行代理模块

提供工具执行的代理方法，委托给 ToolExecutor。
"""

from typing import TYPE_CHECKING, Any

from src.tools.utils import is_parse_failed, parse_tool_arguments

if TYPE_CHECKING:
    from src.sandbox_core._path import PathMapper, PermissionChecker
    from src.sandbox_core._execution import ToolExecutor


class ToolExecutionMixin:
    """工具执行 mixin

    提供工具执行方法，委托给核心组件。
    子类需要提供:
    - _path_mapper: PathMapper
    - _permission_checker: PermissionChecker
    - _tool_executor: ToolExecutor
    """

    _path_mapper: Any  # PathMapper
    _permission_checker: Any  # PermissionChecker
    _tool_executor: Any  # ToolExecutor

    async def execute_tools_proxy(
        self: Any, tool_calls: list[dict]
    ) -> list[dict[str, Any]]:
        """在隔离环境中执行工具（代理方法）"""
        results: list[dict[str, Any]] = []
        for tc in tool_calls:
            result = await self._execute_single_tool_proxy(tc)
            results.append(result)
        return results

    async def _execute_single_tool_proxy(
        self: Any, tool_call: dict
    ) -> dict[str, Any]:
        """执行单个工具（代理方法）"""
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

        mapped_args = self._path_mapper.map_paths(tool_args)
        if not self._permission_checker.check_permission(tool_name, mapped_args):
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"Error: Permission denied for tool '{tool_name}' in sandbox",
            }

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


__all__ = ["ToolExecutionMixin"]