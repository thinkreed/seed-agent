"""
Circuit Breaker 类型定义

熔断器相关的数据类型：状态枚举、配置类、统计类。
"""

from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"      # 熔断状态（拒绝请求）
    HALF_OPEN = "half_open"  # 半开状态（探测恢复）


@dataclass
class CircuitConfig:
    """熔断器配置"""
    failure_threshold: int = 3       # 连续失败次数触发熔断
    recovery_timeout: float = 30.0   # 熔断后等待恢复的秒数
    half_open_max_calls: int = 1     # 半开状态最大探测次数
    success_threshold: int = 2       # 半开状态成功次数恢复正常


@dataclass
class CircuitStats:
    """熔断器统计"""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = 0.0
    total_failures: int = 0
    total_successes: int = 0
    total_rejections: int = 0