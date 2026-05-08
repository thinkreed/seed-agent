"""Timer 辅助函数模块

提供简化的时间计算函数。
"""

import time


def measure_duration(start_time: float) -> float:
    """计算持续时间（毫秒）

    Args:
        start_time: 开始时间（time.time() 返回值）

    Returns:
        float: 持续时间（毫秒）

    Example:
        start = time.time()
        # ... 执行操作 ...
        duration_ms = measure_duration(start)
    """
    return (time.time() - start_time) * 1000


def measure_duration_sec(start_time: float) -> float:
    """计算持续时间（秒）

    Args:
        start_time: 开始时间（time.time() 返回值）

    Returns:
        float: 持续时间（秒）
    """
    return time.time() - start_time