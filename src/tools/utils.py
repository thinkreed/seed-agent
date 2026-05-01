"""工具辅助函数模块

提供工具参数解析、错误处理等公共功能。
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


def parse_tool_arguments(raw_args: str | dict | None) -> dict:
    """鲁棒地解析工具参数

    Args:
        raw_args: 原始参数，可能是 JSON 字符串、字典或 None

    Returns:
        dict: 解析后的参数字典

    Examples:
        >>> parse_tool_arguments('{"path": "/tmp/file.txt"}')
        {'path': '/tmp/file.txt'}
        >>> parse_tool_arguments('')
        {}
        >>> parse_tool_arguments(None)
        {}
    """
    try:
        if isinstance(raw_args, str):
            raw_args = raw_args.strip()
            return json.loads(raw_args) if raw_args else {}
        elif isinstance(raw_args, dict):
            return raw_args
        else:
            return {}
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Invalid tool args: {raw_args!r}, using empty dict. Error: {e}")
        return {}


def format_tool_error(error: Exception, tool_name: str = "unknown") -> str:
    """格式化工具执行错误信息

    Args:
        error: 异常对象
        tool_name: 工具名称

    Returns:
        str: 格式化的错误信息
    """
    error_type = type(error).__name__
    error_msg = str(error)[:200]  # 截断长错误信息
    return f"Error in {tool_name}: {error_type} - {error_msg}"


def is_recoverable_error(error: Exception) -> bool:
    """判断异常是否可恢复（应转换为错误响应而非传播）

    Args:
        error: 异常对象

    Returns:
        bool: True 表示可恢复，False 表示应传播
    """
    # 应传播的异常（不可恢复）
    unrecoverable = (
        asyncio.CancelledError,
        KeyboardInterrupt,
        SystemExit,
    )

    # 避免导入 asyncio，使用类型名检查
    if type(error).__name__ == "CancelledError":
        return False

    return not isinstance(error, unrecoverable)