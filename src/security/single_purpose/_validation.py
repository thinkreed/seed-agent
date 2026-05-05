"""
单用途工具验证逻辑

包含参数验证和用户确认逻辑
"""

import logging
from collections.abc import Callable
from typing import Any

from src.security.single_purpose._config import SinglePurposeToolConfig

logger = logging.getLogger(__name__)


def validate_args(
    config: SinglePurposeToolConfig,
    args: dict[str, Any],
) -> dict[str, Any]:
    """验证参数

    Args:
        config: 工具配置
        args: 用户提供的参数

    Returns:
        验证后的参数字典

    Raises:
        ValueError: 参数验证失败
    """
    validated: dict[str, Any] = {}

    for arg_name, arg_schema in config.args_schema.items():
        # 获取参数值
        if arg_name in args:
            value = args[arg_name]
        elif "default" in arg_schema:
            value = arg_schema["default"]
        elif arg_schema.get("required"):
            raise ValueError(f"Missing required argument: {arg_name}")
        else:
            continue

        # 类型检查
        expected_type = arg_schema.get("type", "string")
        if expected_type == "string" and not isinstance(value, str):
            value = str(value)
        elif expected_type == "integer" and not isinstance(value, int):
            try:
                value = int(value)
            except ValueError as e:
                raise ValueError(f"Argument {arg_name} must be integer") from e
        elif expected_type == "boolean" and not isinstance(value, bool):
            value = str(value).lower() in ("true", "yes", "1")

        # enum 检查
        if "enum" in arg_schema and value not in arg_schema["enum"]:
            raise ValueError(f"Argument {arg_name} must be one of: {arg_schema['enum']}")

        validated[arg_name] = value

    return validated


def request_confirmation(
    tool_name: str,
    args: dict[str, Any],
    confirmation_callback: Callable | None,
) -> bool:
    """请求用户确认

    Args:
        tool_name: 工具名称
        args: 工具参数
        confirmation_callback: 用户确认回调函数

    Returns:
        是否获得确认
    """
    if confirmation_callback:
        return confirmation_callback(tool_name, args)

    # 默认行为：记录警告并返回 False（需要外部确认机制）
    logger.warning(f"Tool {tool_name} requires confirmation but no callback set")
    return False