"""工具辅助函数模块

提供工具参数解析、错误处理、后台任务管理等公共功能。
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 解析失败标记 - 用于区分 "成功解析的空字典 {}" 和 "解析失败"
PARSE_FAILED: dict[str, Any] = {"__parse_failed__": True}

# 全局后台任务集合（防止 asyncio.create_task 返回值被垃圾回收）
_background_tasks: set[asyncio.Task[Any]] = set()
_MAX_BACKGROUND_TASKS = 100  # 最大后台任务数，防止内存泄漏


def safe_int_convert(value: Any, default: int, min_val: int = 1) -> int:
    """安全地将值转换为整数

    用于处理 LLM 返回字符串类型数值参数的情况：
    - LLM 可能返回 "timeout": "300" (JSON 字符串)
    - asyncio.wait_for 内部会执行 timeout <= 0 比较
    - 字符串与整数比较会导致 TypeError

    Args:
        value: 要转换的值（可能是 str, int, float, None 等）
        default: 转换失败时的默认值
        min_val: 最小有效值

    Returns:
        int: 转换后的整数，或默认值
    """
    if value is None:
        return default

    try:
        result = int(value)
        if result < min_val:
            logger.warning(
                f"Converted value {result} < min_val {min_val}, using default {default}"
            )
            return default
        return result
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Failed to convert {value!r} to int: {e}, using default {default}"
        )
        return default


def add_background_task(task: asyncio.Task[Any]) -> None:
    """安全添加后台任务，超过限制时自动清理已完成任务

    Args:
        task: asyncio Task 对象

    Note:
        - 任务完成后自动从集合中移除
        - 超过 _MAX_BACKGROUND_TASKS 时清理已完成任务
        - 用于防止 Task 对象被垃圾回收导致任务取消
    """
    # 如果超过最大限制，清理已完成任务
    if len(_background_tasks) >= _MAX_BACKGROUND_TASKS:
        done_tasks = [t for t in _background_tasks if t.done()]
        for t in done_tasks:
            _background_tasks.discard(t)
        if done_tasks:
            logger.debug(f"Cleaned {len(done_tasks)} completed background tasks")

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def parse_tool_arguments(raw_args: str | dict | None) -> dict[str, Any]:
    """鲁棒地解析工具参数

    Args:
        raw_args: 原始参数，可能是 JSON 字符串、字典或 None

    Returns:
        dict: 解析后的参数字典。如果解析失败，返回 PARSE_FAILED 标记字典。

    Examples:
        >>> parse_tool_arguments('{"path": "/tmp/file.txt"}')
        {'path': '/tmp/file.txt'}
        >>> parse_tool_arguments('{}')
        {}
        >>> parse_tool_arguments('')
        {}
        >>> parse_tool_arguments(None)
        {}
        >>> parse_tool_arguments('invalid json')
        {'__parse_failed__': True}
        >>> parse_tool_arguments('["invalid"]')  # 非 dict JSON
        {'__parse_failed__': True}
    """
    try:
        if isinstance(raw_args, str):
            raw_args = raw_args.strip()
            if not raw_args or raw_args == "{}":
                # 空字符串或空 JSON 对象 -> 空字典（合法）
                return {}
            parsed = json.loads(raw_args)
            # 确保 JSON 解析结果是 dict 类型
            if isinstance(parsed, dict):
                return parsed
            # 非 dict JSON（如 list）视为失败
            logger.warning(f"Invalid tool args (not a dict): {raw_args!r}")
            return PARSE_FAILED
        if isinstance(raw_args, dict):
            # 已经是 dict，直接返回（可能是 PARSE_FAILED 或其他）
            return raw_args
        return {}
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Invalid tool args: {raw_args!r}, parse failed. Error: {e}")
        return PARSE_FAILED


def is_parse_failed(args: dict[str, Any]) -> bool:
    """检查参数是否为解析失败标记

    Args:
        args: 解析后的参数字典

    Returns:
        bool: True 表示解析失败
    """
    return args is PARSE_FAILED or args.get("__parse_failed__") is True


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
