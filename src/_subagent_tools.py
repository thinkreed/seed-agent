"""
Subagent 工具管理模块

包含工具设置、过滤、执行
"""

import logging

from src._subagent_config import (
    PERMISSION_SETS,
    SUBAGENT_SYSTEM_PROMPTS,
    SUBAGENT_TYPE_PERMISSIONS,
)
from src._subagent_types import SubagentType, _get_subagent_type_key
from src.tools import ToolRegistry
from src.tools.utils import parse_tool_arguments

logger = logging.getLogger(__name__)


def setup_tools(
    tools: ToolRegistry,
    subagent_type: SubagentType,
    custom_tools: set[str] | None = None,
) -> set[str]:
    """设置工具集"""
    type_key = _get_subagent_type_key(subagent_type)
    if custom_tools:
        allowed_tools = custom_tools
    else:
        permission_set_name = SUBAGENT_TYPE_PERMISSIONS[type_key]
        allowed_tools = PERMISSION_SETS[permission_set_name]

    from src.tools.builtin_tools import register_builtin_tools
    from src.tools.memory_tools import register_memory_tools

    register_builtin_tools(tools)
    register_memory_tools(tools)

    filter_tools(tools, allowed_tools)

    return allowed_tools


def filter_tools(tools: ToolRegistry, allowed: set[str]) -> None:
    """只保留允许的工具"""
    tools._tools = {
        name: tool for name, tool in tools._tools.items() if name in allowed
    }
    tools._tool_schemas = {
        name: schema
        for name, schema in tools._tool_schemas.items()
        if name in allowed
    }


async def execute_tool_calls(tools: ToolRegistry, tool_calls: list[dict]) -> list[dict]:
    """执行工具调用"""
    results = []
    for tool_call in tool_calls:
        tool_id = tool_call["id"]
        tool_name = tool_call["function"]["name"]
        tool_args = parse_tool_arguments(tool_call["function"]["arguments"])

        try:
            result = await tools.execute(tool_name, **tool_args)
            results.append(
                {"role": "tool", "tool_call_id": tool_id, "content": str(result)}
            )
        except Exception as e:
            error_type = type(e).__name__
            full_error_msg = str(e)
            truncated_msg = full_error_msg[:200]
            logger.exception(f"Tool {tool_name} failed: {error_type}: {full_error_msg}")
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": f"Error in {tool_name}: {error_type} - {truncated_msg}",
                }
            )

    return results


def get_system_prompt(subagent_type: SubagentType, custom: str | None = None) -> str:
    """获取系统提示"""
    base_prompt = SUBAGENT_SYSTEM_PROMPTS[_get_subagent_type_key(subagent_type)]
    return custom or base_prompt