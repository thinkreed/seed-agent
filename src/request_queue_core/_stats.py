"""
请求队列统计模块

处理队列统计和智能调整逻辑。
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.request_queue_core._types import (
    MAX_BACKPRESSURE_THRESHOLD,
    MAX_CRITICAL_DISPATCH_RATE,
    MAX_CRITICAL_QUEUE_SIZE,
    MAX_NORMAL_DISPATCH_RATE,
    STATS_WINDOW_SIZE,
    RequestPriority,
)

logger = logging.getLogger("seed_agent")


@dataclass
class QueueStats:
    """队列统计"""

    # 等待时间记录
    wait_times: dict[RequestPriority, list[float]] = field(
        default_factory=lambda: {p: [] for p in RequestPriority}
    )

    # 计数
    submitted: dict[RequestPriority, int] = field(
        default_factory=lambda: dict.fromkeys(RequestPriority, 0)
    )
    signaled: dict[RequestPriority, int] = field(
        default_factory=lambda: dict.fromkeys(RequestPriority, 0)
    )
    rejected: dict[RequestPriority, int] = field(
        default_factory=lambda: dict.fromkeys(RequestPriority, 0)
    )
    cancelled: dict[RequestPriority, int] = field(
        default_factory=lambda: dict.fromkeys(RequestPriority, 0)
    )

    def record_submit(self, priority: RequestPriority) -> None:
        self.submitted[priority] += 1

    def record_signal(self, priority: RequestPriority) -> None:
        self.signaled[priority] += 1

    def record_rejected(self, priority: RequestPriority) -> None:
        self.rejected[priority] += 1

    def record_cancelled(self, priority: RequestPriority) -> None:
        self.cancelled[priority] += 1

    def record_wait_time(self, priority: RequestPriority, duration: float) -> None:
        self.wait_times[priority].append(duration)
        if len(self.wait_times[priority]) > STATS_WINDOW_SIZE:
            self.wait_times[priority] = self.wait_times[priority][-STATS_WINDOW_SIZE:]

    def get_avg_wait_time(self, priority: RequestPriority) -> float:
        times = self.wait_times[priority]
        if not times:
            return 0.0
        return sum(times) / len(times)

    def get_p95_wait_time(self, priority: RequestPriority) -> float:
        times = self.wait_times[priority]
        if not times:
            return 0.0
        sorted_times = sorted(times)
        idx = int(len(sorted_times) * MAX_BACKPRESSURE_THRESHOLD)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def get_reject_rate(self, priority: RequestPriority) -> float:
        submitted = self.submitted[priority]
        if submitted == 0:
            return 0.0
        return self.rejected[priority] / submitted

    def get_stats_dict(self) -> dict[str, Any]:
        return {
            "submitted": {p.name: self.submitted[p] for p in RequestPriority},
            "signaled": {p.name: self.signaled[p] for p in RequestPriority},
            "rejected": {p.name: self.rejected[p] for p in RequestPriority},
            "cancelled": {p.name: self.cancelled[p] for p in RequestPriority},
            "avg_wait_times": {
                p.name: self.get_avg_wait_time(p) for p in RequestPriority
            },
            "p95_wait_times": {
                p.name: self.get_p95_wait_time(p) for p in RequestPriority
            },
            "reject_rates": {p.name: self.get_reject_rate(p) for p in RequestPriority},
        }


class ConfigAdjuster:
    """智能配置调整器"""

    def adjust_config(self, config: Any, stats: QueueStats) -> None:
        """根据统计数据智能调整配置"""
        from src.request_queue_core._types import (
            BACKPRESSURE_INCREMENT,
            CRITICAL_SIZE_INCREMENT,
            DISPATCH_RATE_MULTIPLIER,
            REJECT_RATE_THRESHOLD,
        )

        # CRITICAL 队列调整
        critical_avg_wait = stats.get_avg_wait_time(RequestPriority.CRITICAL)
        critical_p95_wait = stats.get_p95_wait_time(RequestPriority.CRITICAL)

        if critical_avg_wait > config.critical_target_wait_time:
            old_rate = config.critical_dispatch_rate
            config.critical_dispatch_rate *= DISPATCH_RATE_MULTIPLIER
            config.critical_dispatch_rate = min(
                config.critical_dispatch_rate, MAX_CRITICAL_DISPATCH_RATE
            )

            if config.critical_dispatch_rate != old_rate:
                logger.info(
                    f"Auto-adjust: CRITICAL dispatch_rate increased to "
                    f"{config.critical_dispatch_rate:.2f}"
                )

            if critical_p95_wait > config.critical_target_wait_time * 2:
                old_size = config.critical_max_size
                config.critical_max_size = min(
                    config.critical_max_size + CRITICAL_SIZE_INCREMENT,
                    MAX_CRITICAL_QUEUE_SIZE,
                )
                if config.critical_max_size != old_size:
                    logger.info(
                        f"Auto-adjust: CRITICAL max_size increased to "
                        f"{config.critical_max_size}"
                    )

        # 反压阈值调整
        critical_reject_rate = stats.get_reject_rate(RequestPriority.CRITICAL)

        if critical_reject_rate > REJECT_RATE_THRESHOLD:
            old_threshold = config.critical_backpressure_threshold
            config.critical_backpressure_threshold = min(
                config.critical_backpressure_threshold + BACKPRESSURE_INCREMENT,
                MAX_BACKPRESSURE_THRESHOLD,
            )
            if config.critical_backpressure_threshold != old_threshold:
                logger.info(
                    f"Auto-adjust: CRITICAL backpressure_threshold increased to "
                    f"{config.critical_backpressure_threshold:.2f}"
                )

        # 普通队列调整
        normal_avg_wait = stats.get_avg_wait_time(RequestPriority.NORMAL)
        if normal_avg_wait > config.normal_target_wait_time:
            old_rate = config.normal_dispatch_rate
            config.normal_dispatch_rate *= DISPATCH_RATE_MULTIPLIER
            config.normal_dispatch_rate = min(
                config.normal_dispatch_rate, MAX_NORMAL_DISPATCH_RATE
            )

            if config.normal_dispatch_rate != old_rate:
                logger.info(
                    f"Auto-adjust: NORMAL dispatch_rate increased to "
                    f"{config.normal_dispatch_rate:.2f}"
                )