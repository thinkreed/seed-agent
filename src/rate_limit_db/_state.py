"""限流状态数据结构

RateLimitState: 完整的限流状态数据类
"""

from dataclasses import dataclass, field


@dataclass
class RateLimitState:
    """完整的限流状态"""

    timestamp: float
    tokens_available: float = 100.0
    last_refill_time: float = 0.0
    requests_in_window: list[float] = field(default_factory=list)
    total_requests_lifetime: int = 0