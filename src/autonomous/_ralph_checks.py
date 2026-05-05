"""Ralph Loop 检查模块

包含 Ralph Loop 的安全检查和防御检查逻辑。
"""

import logging
from typing import TYPE_CHECKING

from src.autonomous._executor_constants import (
    RALPH_MAX_DURATION,
    RALPH_MAX_ITERATIONS,
)
from src.ralph_state import check_safety_limits as check_global_safety_limits

if TYPE_CHECKING:
    from src.autonomous._executor_core import TaskExecutor

logger = logging.getLogger("seed_agent")


def check_iteration_budget(executor: "TaskExecutor", iteration: int, budget: int) -> bool:
    """检查迭代预算

    Args:
        executor: TaskExecutor 实例
        iteration: 当前迭代次数
        budget: 预算上限

    Returns:
        bool: 是否应该终止循环
    """
    # 预算上限检查
    if iteration >= budget:
        logger.info(f"迭代预算耗尽 ({iteration}/{budget}), 结束循环")
        return True
    return False


def check_safety_limits(executor: "TaskExecutor") -> bool:
    """检查安全上限（防止无限循环）

    Args:
        executor: TaskExecutor 实例

    Returns:
        bool: 是否应该终止循环
    """
    if check_global_safety_limits(
        iteration=executor._state_manager.get_iteration_count(),
        max_iterations=RALPH_MAX_ITERATIONS,
        start_time=executor._state_manager.get_start_time(),
        accumulated_duration=executor._state_manager.get_accumulated_duration(),
        max_duration=RALPH_MAX_DURATION,
    ):
        logger.info(
            "Ralph Loop safety limit reached, cleaning up state for next session"
        )
        executor._state_manager.cleanup_state()
        return True
    return False


def check_defense_layers(executor: "TaskExecutor", iteration: int, budget: int) -> bool:
    """执行四层防御检查

    Args:
        executor: TaskExecutor 实例
        iteration: 当前迭代次数
        budget: 预算上限

    Returns:
        bool: 是否应该终止循环
    """
    # Layer 1: 预算警告注入
    # (已在 ralph_loop 中异步处理)

    # Layer 2: 进度检测窗口
    if not executor._defense.check_progress_window():
        logger.info("进度检测判定空转，提前终止")
        return True

    # Layer 3: 时间断路器
    if not executor._defense.check_time_circuit_breaker(executor.agent):
        logger.info("时间断路器触发，强制终止")
        return True

    return False


def check_completion_markers(response: str | None, markers: list[str]) -> bool:
    """检查完成标记

    Args:
        response: 当前响应
        markers: 完成标记列表

    Returns:
        bool: 是否检测到完成
    """
    if response and any(marker in response for marker in markers):
        return True
    return False


__all__ = [
    "check_iteration_budget",
    "check_safety_limits",
    "check_defense_layers",
    "check_completion_markers",
]