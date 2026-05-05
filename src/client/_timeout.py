"""
动态超时配置模块

提供:
- TimeoutConfig: 等待超时配置（可动态调整）
"""

from dataclasses import dataclass, field

from src.request_queue import RequestPriority


@dataclass
class TimeoutConfig:
    """等待超时配置（可动态调整）

    基于负载因子动态调整超时时间：
    - 高负载：延长超时，给更多等待时间
    - 低负载：缩短超时，快速处理或快速失败
    """

    # 基础超时（秒）
    base_timeouts: dict[RequestPriority, float] = field(
        default_factory=lambda: {
            RequestPriority.CRITICAL: 30.0,
            RequestPriority.HIGH: 60.0,
            RequestPriority.NORMAL: 120.0,
            RequestPriority.LOW: 300.0,
        }
    )

    # 动态调整参数
    auto_adjust_enabled: bool = True
    load_factor_threshold: float = 0.7
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0

    def get_timeout(self, priority: RequestPriority, load_factor: float) -> float:
        """获取动态超时

        Args:
            priority: 请求优先级
            load_factor: 当前负载因子（0.0-1.0）

        Returns:
            动态超时时间（秒）
        """
        base = self.base_timeouts.get(priority, 120.0)

        if load_factor > self.load_factor_threshold:
            # 高负载：延长超时，给更多等待时间
            excess = load_factor - self.load_factor_threshold
            multiplier = 1.0 + excess * 1.5
            multiplier = min(multiplier, self.max_multiplier)
        else:
            # 低负载：缩短超时，快速处理或快速失败
            deficit = self.load_factor_threshold - load_factor
            multiplier = 1.0 - deficit * 0.5
            multiplier = max(multiplier, self.min_multiplier)

        return base * multiplier
