"""Ralph Loop 主循环模块

包含 Ralph Loop 的核心执行逻辑。
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.autonomous._executor_constants import (
    COMPLETION_MARKERS,
    CONTEXT_RESET_ENABLED,
    CONTEXT_RESET_INTERVAL,
    RALPH_MAX_DURATION,
    RALPH_MAX_ITERATIONS,
)
from src.ralph_state import check_safety_limits
from src.session_event_stream import EventType
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

        # Layer 1: 预算警告注入
        await executor._defense.inject_budget_warning(
            iteration, budget, executor.agent
        )

        # Layer 2: 进度检测窗口
        if not executor._defense.check_progress_window():
            logger.info("进度检测判定空转，提前终止")
            break

        # Layer 3: 时间断路器
        if not executor._defense.check_time_circuit_breaker(executor.agent):
            logger.info("时间断路器触发，强制终止")
            break

        # 安全上限检查
        if executor._check_safety_limits():
            logger.info(
                "Ralph Loop safety limit reached, cleaning up state for next session"
            )
            executor._state_manager.cleanup_state()
            break

        # 预算上限检查
        if iteration >= budget:
            logger.info(f"迭代预算耗尽 ({iteration}/{budget}), 结束循环")
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
        try:
            response = await asyncio.wait_for(
                executor.agent.run(next_prompt, wait_for_user=False),
                timeout=llm_timeout,
            )

            # 记录工具调用历史
            executor._record_tool_calls()

            if debug_enabled:
                logger.debug(
                    f"[Ralph Loop] Iteration {iteration}: "
                    f"response='{response[:200] if response else 'None'}...', "
                    f"length={len(response) if response else 0}"
                )

            consecutive_failures = 0

        except TimeoutError:
            logger.warning(
                f"[Ralph Loop] Iteration {iteration}: "
                f"LLM call timeout ({llm_timeout}s), skipping iteration"
            )
            consecutive_failures += 1
            response = f"[TIMEOUT] LLM call exceeded {llm_timeout}s limit"

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
            consecutive_failures += 1
            response = f"Error: {type(e).__name__}: {e!s}"

        except Exception as e:
            logger.exception(
                f"[Ralph Loop] Iteration {iteration}: "
                f"Unexpected error: {type(e).__name__}"
            )
            consecutive_failures += 1
            response = f"Unexpected Error: {type(e).__name__}: {e!s}"

        # === 状态持久化 ===
        executor._state_manager.persist_state(response or "")

        # === 错误恢复退避 ===
        if consecutive_failures >= failure_threshold:
            backoff = min(
                backoff_duration * (2 ** (consecutive_failures - failure_threshold)),
                max_backoff,
            )
            logger.warning(
                f"[Ralph Loop] Consecutive failures {consecutive_failures}, "
                f"backing off for {backoff}s"
            )
            await asyncio.sleep(backoff)
            if consecutive_failures >= failure_threshold * 2:
                consecutive_failures = 0

        # === 完成检测 ===
        if response and any(marker in response for marker in COMPLETION_MARKERS):
            logger.info(f"Autonomous exploration completed at iteration {iteration}")
            executor._state_manager.cleanup_state()
            break

        # === 下一轮 prompt ===
        next_prompt = await executor._handle_response(response) or "继续执行自主探索任务"
        await asyncio.sleep(2)

    return response


def check_safety_limits(
    iteration: int,
    start_time: float,
    accumulated_duration: float,
) -> bool:
    """检查安全上限（防止无限循环）

    Args:
        iteration: 当前迭代次数
        start_time: 开始时间
        accumulated_duration: 累计持续时间

    Returns:
        bool: 是否达到安全上限
    """
    # 迭代次数上限
    if iteration >= RALPH_MAX_ITERATIONS:
        return True

    # 执行时间上限
    total_duration = accumulated_duration
    if start_time > 0:
        import time
        total_duration += time.time() - start_time

    if total_duration >= RALPH_MAX_DURATION:
        return True

    return False


__all__ = ["run_ralph_loop", "check_safety_limits"]