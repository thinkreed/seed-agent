"""Ralph Loop 执行模块

包含 LLM 调用和错误处理逻辑。
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.autonomous._executor_core import TaskExecutor

logger = logging.getLogger("seed_agent")


async def execute_llm_call(
    executor: "TaskExecutor",
    iteration: int,
    prompt: str,
    timeout: float,
    consecutive_failures: int,
    debug_enabled: bool,
) -> tuple[str | None, int]:
    """执行 LLM 调用（带超时保护）

    Args:
        executor: TaskExecutor 实例
        iteration: 当前迭代次数
        prompt: 执行 prompt
        timeout: 超时秒数
        consecutive_failures: 当前连续失败次数
        debug_enabled: 是否启用调试日志

    Returns:
        tuple[str | None, int]: (响应文本, 更新后的失败次数)
    """
    try:
        response = await asyncio.wait_for(
            executor.agent.run(prompt, wait_for_user=False),
            timeout=timeout,
        )

        executor._record_tool_calls()

        if debug_enabled:
            logger.debug(
                f"[Ralph Loop] Iteration {iteration}: "
                f"response='{response[:200] if response else 'None'}...', "
                f"length={len(response) if response else 0}"
            )

        return response, 0

    except TimeoutError:
        logger.warning(
            f"[Ralph Loop] Iteration {iteration}: "
            f"LLM call timeout ({timeout}s), skipping"
        )
        return f"[TIMEOUT] LLM call exceeded {timeout}s limit", consecutive_failures + 1

    except (RuntimeError, OSError, ValueError, asyncio.CancelledError, KeyError) as e:
        logger.warning(
            f"[Ralph Loop] Iteration {iteration}: "
            f"Agent error: {type(e).__name__}: {e!s}"
        )
        return f"Error: {type(e).__name__}: {e!s}", consecutive_failures + 1

    except Exception as e:
        logger.exception(
            f"[Ralph Loop] Iteration {iteration}: "
            f"Unexpected error: {type(e).__name__}"
        )
        return f"Unexpected Error: {type(e).__name__}: {e!s}", consecutive_failures + 1


async def handle_error_backoff(
    consecutive_failures: int,
    threshold: int,
    base_duration: float,
    max_duration: float,
) -> int:
    """处理错误恢复退避

    Args:
        consecutive_failures: 当前连续失败次数
        threshold: 触发退避的阈值
        base_duration: 基础退避时长
        max_duration: 最大退避时长

    Returns:
        int: 更新后的失败次数
    """
    if consecutive_failures >= threshold:
        backoff = min(
            base_duration * (2 ** (consecutive_failures - threshold)),
            max_duration,
        )
        logger.warning(
            f"[Ralph Loop] Consecutive failures {consecutive_failures}, "
            f"backing off for {backoff}s"
        )
        await asyncio.sleep(backoff)

        if consecutive_failures >= threshold * 2:
            return 0

    return consecutive_failures


__all__ = ["execute_llm_call", "handle_error_backoff"]