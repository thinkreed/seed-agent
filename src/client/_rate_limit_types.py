"""
限流类型和配置模块

提供:
- RateLimitTimeoutError: 自定义限流超时异常
- load_queue_config: 加载队列配置
"""

from typing import Any

from src.request_queue import QueueConfig


# 使用自定义限流异常，避免 OpenAI SDK 的类型限制
class RateLimitTimeoutError(Exception):
    """自定义限流等待超时异常"""

    def __init__(self, message: str = "Rate limit wait timeout") -> None:
        super().__init__(message)


def load_queue_config(config: Any) -> QueueConfig:
    """从配置加载 QueueConfig

    Args:
        config: FullConfig 实例

    Returns:
        QueueConfig 实例
    """
    # 尝试从 FullConfig 的 queue 字段加载
    if hasattr(config, "queue") and config.queue:
        return QueueConfig(
            critical_max_size=config.queue.critical_max_size,
            critical_backpressure_threshold=config.queue.critical_backpressure_threshold,
            critical_dispatch_rate=config.queue.critical_dispatch_rate,
            critical_target_wait_time=config.queue.critical_target_wait_time,
            normal_max_size=config.queue.normal_max_size,
            normal_backpressure_threshold=config.queue.normal_backpressure_threshold,
            normal_dispatch_rate=config.queue.normal_dispatch_rate,
            normal_target_wait_time=config.queue.normal_target_wait_time,
            auto_adjust_enabled=config.queue.auto_adjust_enabled,
        )

    # 使用默认值
    return QueueConfig()