"""
请求队列统计数据结构

提取 QueueStats 类。
"""

from dataclasses import dataclass, field
from typing import Any

from src.request_queue_core._types import (
    MAX_BACKPRESSURE_THRESHOLD,
    STATS_WINDOW_SIZE,
    RequestPriority,
)


@dataclass
class QueueStats:
    """队列统计"""

    wait_times: dict[RequestPriority, list[float]] = field(
        default_factory=lambda: {p: [] for p in RequestPriority}
    )
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
            "avg_wait_times": {p.name: self.get_avg_wait_time(p) for p in RequestPriority},
            "p95_wait_times": {p.name: self.get_p95_wait_time(p) for p in RequestPriority},
            "reject_rates": {p.name: self.get_reject_rate(p) for p in RequestPriority},
        }


__all__ = ["QueueStats"]