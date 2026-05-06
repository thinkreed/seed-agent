"""
请求队列 - 指标模块

处理队列填充率和统计信息计算。
"""

from typing import Any


class QueueMetrics:
    """队列指标计算器"""

    def __init__(
        self,
        critical_queue,
        normal_queues,
        config,
        stats,
        running: bool,
    ):
        self._critical_queue = critical_queue
        self._normal_queues = normal_queues
        self._config = config
        self._stats = stats
        self._running = running

    def get_critical_fill_ratio(self) -> float:
        """获取 CRITICAL 队列填充率"""
        return len(self._critical_queue) / self._config.critical_max_size

    def get_normal_fill_ratio(self) -> float:
        """获取普通队列填充率"""
        total = sum(len(q) for q in self._normal_queues.values())
        return total / self._config.normal_max_size

    def get_total_fill_ratio(self) -> float:
        """获取总体队列填充率"""
        critical_fill = self.get_critical_fill_ratio()
        normal_fill = self.get_normal_fill_ratio()
        return critical_fill * 0.2 + normal_fill * 0.8

    def get_queue_size(self) -> dict[str, int]:
        """获取各队列大小"""
        return {
            "critical": len(self._critical_queue),
            "high": len(self._normal_queues[RequestPriority.HIGH]),
            "normal": len(self._normal_queues[RequestPriority.NORMAL]),
            "low": len(self._normal_queues[RequestPriority.LOW]),
            "total": len(self._critical_queue)
            + sum(len(q) for q in self._normal_queues.values()),
        }

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息"""
        return {
            "queue_lengths": self.get_queue_size(),
            "fill_ratios": {
                "critical": self.get_critical_fill_ratio(),
                "normal": self.get_normal_fill_ratio(),
                "total": self.get_total_fill_ratio(),
            },
            "config": {
                "critical_max_size": self._config.critical_max_size,
                "critical_backpressure_threshold": self._config.critical_backpressure_threshold,
                "critical_dispatch_rate": self._config.critical_dispatch_rate,
                "normal_max_size": self._config.normal_max_size,
                "normal_backpressure_threshold": self._config.normal_backpressure_threshold,
                "normal_dispatch_rate": self._config.normal_dispatch_rate,
                "auto_adjust_enabled": self._config.auto_adjust_enabled,
            },
            "stats": self._stats.get_stats_dict(),
            "running": self._running,
        }


# 需要导入 RequestPriority
from src.request_queue_core._types import RequestPriority