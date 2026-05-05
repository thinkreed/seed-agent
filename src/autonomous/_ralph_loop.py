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
from src.autonomous._ralph_execution import execute_llm_call, handle_error_backoff
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

    budget = max_budget or config.max_iterations_per_task
    response: str | None = None
    next_prompt: str = "继续执行自主探索任务"
    consecutive_failures: int = 0

    while True:
        iteration = executor._state_manager.increment_iteration()

        # 多层防御检查
        await executor._defense.inject_budget_warning(iteration, budget, executor.agent)

        if check_defense_layers(executor, iteration, budget):
            break

        if check_safety_limits(executor):
            break

        if check_iteration_budget(executor, iteration, budget):
            break

        # 完成标志检查
        if executor._check_completion_promise():
            logger.info("Completion promise detected, exiting Ralph loop")
            executor._state_manager.cleanup_state()
            await executor._notify_completion("DONE")
            return "DONE"

        # 上下文重置
        await executor._reset_context_if_needed()

        if debug_enabled:
            logger.debug(
                f"[Ralph Loop] Iteration {iteration}: "
                f"prompt='{next_prompt[:100]}...', "
                f"failures={consecutive_failures}/{failure_threshold}"
            )

        # LLM 调用
        response, consecutive_failures = await execute_llm_call(
            executor, iteration, next_prompt, llm_timeout, consecutive_failures, debug_enabled
        )

        # 状态持久化
        executor._state_manager.persist_state(response or "")

        # 错误恢复退避
        consecutive_failures = await handle_error_backoff(
            consecutive_failures, failure_threshold, backoff_duration, max_backoff
        )

        # 完成检测
        if check_completion_markers(response, COMPLETION_MARKERS):
            logger.info(f"Autonomous exploration completed at iteration {iteration}")
            executor._state_manager.cleanup_state()
            break

        # 下一轮 prompt
        next_prompt = await executor._handle_response(response) or "继续执行自主探索任务"
        await asyncio.sleep(2)

    return response


__all__ = ["run_ralph_loop"]