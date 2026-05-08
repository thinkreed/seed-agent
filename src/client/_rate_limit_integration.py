"""
限流集成模块

提供:
- RateLimitTimeoutError: 自定义限流超时异常
- init_rate_limiting: 初始化限流组件
- load_queue_config: 加载队列配置
- wait_for_turn_and_acquire: 阶段1-2-3排队等待
- execute_with_concurrency_and_rate_limit: 阶段2-4并发执行
- stream_with_concurrency_and_rate_limit: 阶段2-4流式执行

API 兼容层：从子模块导入并重新导出
"""

from ._rate_limit_executor import (
    execute_with_concurrency_and_rate_limit,
    stream_with_concurrency_and_rate_limit,
)
from ._rate_limit_queue import wait_for_turn_and_acquire
from ._rate_limit_types import RateLimitTimeoutError, load_queue_config

__all__ = [
    "RateLimitTimeoutError",
    "load_queue_config",
    "wait_for_turn_and_acquire",
    "execute_with_concurrency_and_rate_limit",
    "stream_with_concurrency_and_rate_limit",
]