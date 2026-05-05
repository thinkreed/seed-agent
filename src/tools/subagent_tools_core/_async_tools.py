"""
Subagent 异步工具模块

提供异步风格的 Subagent 工具：
- wait_for_subagent_async: 异步等待子代理完成

核心特性：
- 支持超时等待
- 真正的异步执行
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from src.tools.utils import safe_int_convert

if TYPE_CHECKING:
    from src.subagent_manager import SubagentManager

logger = logging.getLogger(__name__)

# 引用同步模块的全局变量
from ._sync_tools import _subagent_manager


async def wait_for_subagent_async(
    task_id: str,
    timeout: float | None = None,
) -> str:
    """等待子代理完成并返回结果（异步版本）"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return result.summary

    safe_timeout = None
    if timeout is not None:
        safe_timeout = safe_int_convert(timeout, default=60, min_val=1)

    try:
        if safe_timeout:
            async def wait_loop():
                while True:
                    res = _subagent_manager.get_result(task_id)
                    if res:
                        return res
                    await asyncio.sleep(0.5)

            result = await asyncio.wait_for(wait_loop(), timeout=safe_timeout)
        else:
            while True:
                res = _subagent_manager.get_result(task_id)
                if res:
                    result = res
                    break
                await asyncio.sleep(0.5)

        return result.summary if result else f"Error: No result for task {task_id}"

    except TimeoutError:
        return f"Error: Timeout waiting for subagent {task_id}"
    except Exception as e:
        return f"Error: {e!s}"