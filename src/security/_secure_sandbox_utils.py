"""安全沙盒工具辅助函数"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_single_purpose_tool(tool_factory: Any, tool_name: str) -> bool:
    """检查是否为单用途工具"""
    if tool_factory is None:
        return False
    return tool_factory.get_tool_config(tool_name) is not None


def execute_single_purpose_tool(
    tool_factory: Any,
    tool_name: str,
    args: dict,
) -> str:
    """执行单用途工具"""
    if tool_factory is None:
        return "[ERROR] Single-purpose tool factory not enabled"

    try:
        tool_func = tool_factory.create_tool(tool_name)
        return tool_func(**args)
    except ValueError as e:
        return f"[ERROR] {e}"
    except Exception as e:
        return f"[ERROR] Tool execution failed: {type(e).__name__}: {str(e)[:200]}"


async def execute_standard_tool(tools: Any, tool_name: str, args: dict) -> str:
    """执行标准工具"""
    if not tools:
        raise RuntimeError("Sandbox has no tools registered")
    result = await tools.execute(tool_name, **args)
    return str(result)


async def request_user_approval(
    tool_name: str,
    risk_level: Any,
    args: dict,
    callback: Any,
    user_permission_level: str,
) -> bool:
    """请求用户批准"""
    if callback:
        return callback(tool_name, risk_level.value, args)

    logger.warning(
        f"Tool '{tool_name}' requires user confirmation (risk: {risk_level.value}) "
        f"but no callback configured - defaulting to deny"
    )
    return False