"""
请求队列智能配置调整器

提取 ConfigAdjuster 类。
"""

import logging
from typing import Any

from src.request_queue_core._stats_queue import QueueStats
from src.request_queue_core._types import (
    BACKPRESSURE_INCREMENT,
    CRITICAL_SIZE_INCREMENT,
    DISPATCH_RATE_MULTIPLIER,
    MAX_BACKPRESSURE_THRESHOLD,
    MAX_CRITICAL_DISPATCH_RATE,
    MAX_CRITICAL_QUEUE_SIZE,
    MAX_NORMAL_DISPATCH_RATE,
    REJECT_RATE_THRESHOLD,
    RequestPriority,
)

logger = logging.getLogger("seed_agent")


class ConfigAdjuster:
    """智能配置调整器"""

    def adjust_config(self, config: Any, stats: QueueStats) -> None:
        """根据统计数据智能调整配置"""
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


__all__ = ["ConfigAdjuster"]