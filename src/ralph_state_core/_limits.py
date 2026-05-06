"""
安全上限检查函数

提供迭代/时间双重保护机制。
"""

import logging
import time

logger = logging.getLogger("seed_agent.ralph")


def check_safety_limits(
    iteration: int,
    max_iterations: int,
    start_time: float,
    accumulated_duration: float,
    max_duration: int,
) -> bool:
    """
    检查安全上限（迭代/时间双重保护）

    Args:
        iteration: 当前迭代次数
        max_iterations: 最大迭代次数
        start_time: 当前会话开始时间
        accumulated_duration: 累计执行时间（跨会话）
        max_duration: 最大执行时间（秒）

    Returns:
        True 表示达到上限，需要停止
    """
    # 迭代上限
    if iteration >= max_iterations:
        logger.warning(f"Ralph Loop exceeded max iterations ({max_iterations})")
        return True

    # 时间上限（累计 + 当前会话）
    if start_time > 0:
        current_elapsed = time.time() - start_time
        total_elapsed = accumulated_duration + current_elapsed
        if total_elapsed >= max_duration:
            logger.warning(
                f"Ralph Loop exceeded max duration ({max_duration}s, "
                f"accumulated: {accumulated_duration}s, current: {current_elapsed}s)"
            )
            return True

    return False