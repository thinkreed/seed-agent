"""滚动窗口类型定义

提取 RollingWindowState 和相关常量。
"""

from dataclasses import dataclass


@dataclass
class RollingWindowState:
    """滚动窗口状态（用于持久化）"""

    requests: list[float]  # 时间戳列表
    total_requests_lifetime: int = 0


__all__ = ["RollingWindowState"]