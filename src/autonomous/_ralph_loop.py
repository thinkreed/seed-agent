"""Ralph Loop 主循环模块

包含 Ralph Loop 的核心执行逻辑。
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from src.autonomous._executor_constants import COMPLETION_MARKERS
from src.autonomous._ralph_checks import (
    check_completion_markers,
    check_defense_layers,
    check_iteration_budget,
    check_safety_limits,
)
from src.shared_config import get_autonomous_config

if TYPE_CHECKING:
    from src.autonomous._executor_core import TaskExecutor

logger = logging.getLogger("seed_agent")


async def run_ralph_loop(
    executor: "TaskExecutor",
    max_budget: int | None = None,
) -> str | None:
    """执行 Ralph Loop 主循环（增强版 + 四层防御）

    Args:
        executor: TaskExecutor 实例
        max_budget: 迭代预算上限

    Returns:
        最终响应文本，或 None 表示失败
    """
    config = get_autonomous_config()
    llm_timeout = config.llm_call_timeout_seconds
    failure_threshold = config.consecutive_failure_threshold
    backoff_duration = config.backoff_duration_seconds
    max_backoff = config.max_backoff_multiplier * backoff_duration
    debug_enabled = config.debug_logging_enabled

    # 使用传入预算或配置默认值
    budget = max_budget or config.max_iterations_per_task

    response: str | None = None
    next_prompt: str = "继续执行自主探索任务"
    consecutive_failures: int = 0

    while True:
        iteration = executor._state_manager.increment_iteration()

        # === 多层防御检查 ===
        await executor._defense.inject_budget_warning(
            iteration, budget, executor.agent
        )

        if check_defense_layers(executor, iteration, budget):
            break

        # 安全上限检查
        if check_safety_limits(executor):
            break

        # 预算上限检查
        if check_iteration_budget(executor, iteration, budget):
            break

        # === 完成标志检查 ===
        if executor._check_completion_promise():
            logger.info("Completion promise detected, exiting Ralph loop")
            executor._state_manager.cleanup_state()
            await executor._notify_completion("DONE")
            return "DONE"

        # === 上下文重置 ===
        await executor._reset_context_if_needed()

        # === 调试日志 ===
        if debug_enabled:
            logger.debug(
                f"[Ralph Loop] Iteration {iteration}: "
                f"prompt='{next_prompt[:100]}...', "
                f"failures={consecutive_failures}/{failure_threshold}, "
                f"time_elapsed={executor._defense.get_task_elapsed_time():.0f}s"
            )

        # === LLM 调用（带超时保护）===
        response, consecutive_failures = await _execute_llm_call(
            executor, iteration, next_prompt, llm_timeout, consecutive_failures, debug_enabled
        )

        # === 状态持久化 ===
        executor._state_manager.persist_state(response or "")

        # === 错误恢复退避 ===
        consecutive_failures = await _handle_error_backoff(
            consecutive_failures, failure_threshold, backoff_duration, max_backoff
        )

        # === 完成检测 ===
        if check_completion_markers(response, COMPLETION_MARKERS):
            logger.info(f"Autonomous exploration completed at iteration {iteration}")
            executor._state_manager.cleanup_state()
            break

        # === 下一轮 prompt ===
        next_prompt = await executor._handle_response(response) or "继续执行自主探索任务"
        await asyncio.sleep(2)

    return response


async def _execute_llm_call(
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

        # 记录工具调用历史
        executor._record_tool_calls()

        if debug_enabled:
            logger.debug(
                f"[Ralph Loop] Iteration {iteration}: "
                f"response='{response[:200] if response else 'None'}...', "
                f"length={len(response) if response else 0}"
            )

        return response, 0  # 重置失败计数

    except TimeoutError:
        logger.warning(
            f"[Ralph Loop] Iteration {iteration}: "
            f"LLM call timeout ({timeout}s), skipping iteration"
        )
        return f"[TIMEOUT] LLM call exceeded {timeout}s limit", consecutive_failures + 1

    except (
        RuntimeError,
        OSError,
        ValueError,
        asyncio.CancelledError,
        KeyError,
    ) as e:
        logger.warning(
            f"[Ralph Loop] Iteration {iteration}: "
            f"Agent execution error: {type(e).__name__}: {e!s}"
        )
        return f"Error: {type(e).__name__}: {e!s}", consecutive_failures + 1

    except Exception as e:
        logger.exception(
            f"[Ralph Loop] Iteration {iteration}: "
            f"Unexpected error: {type(e).__name__}"
        )
        return f"Unexpected Error: {type(e).__name__}: {e!s}", consecutive_failures + 1


async def _handle_error_backoff(
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

        # 达到阈值两倍后重置
        if consecutive_failures >= threshold * 2:
            return 0

    return consecutive_failures


__all__ = ["run_ralph_loop", "_execute_llm_call", "_handle_error_backoff"]