"""
请求队列 - 调度器管理模块

处理调度器的启动、停止和自动调整。
"""

import asyncio
import contextlib
import logging

from src.request_queue_core._types import DISPATCH_LOOP_INTERVAL, QueueConfig
from src.request_queue_core._stats import ConfigAdjuster, QueueStats

logger = logging.getLogger("seed_agent")


class QueueManager:
    """调度器生命周期管理"""

    def __init__(
        self,
        config: QueueConfig,
        stats: QueueStats,
        dispatcher,
        new_request_event: asyncio.Event,
    ):
        self._config = config
        self._stats = stats
        self._dispatcher = dispatcher
        self._new_request_event = new_request_event
        self._adjuster = ConfigAdjuster()
        self._dispatcher_task: asyncio.Task | None = None
        self._adjust_task: asyncio.Task | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """调度器是否在运行"""
        return self._running

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning("Dispatcher already running")
            return

        self._running = True
        self._dispatcher.start()
        self._dispatcher_task = asyncio.create_task(self._dispatcher.dispatch_loop())

        if self._config.auto_adjust_enabled:
            self._adjust_task = asyncio.create_task(self._adjust_loop())

        logger.info(
            f"Request queue dispatcher started "
            f"(critical_rate={self._config.critical_dispatch_rate}, "
            f"normal_rate={self._config.normal_dispatch_rate})"
        )

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        self._dispatcher.stop()

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher_task
            self._dispatcher_task = None

        if self._adjust_task:
            self._adjust_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._adjust_task
            self._adjust_task = None

        logger.info("Request queue dispatcher stopped")

    async def _adjust_loop(self) -> None:
        """智能调整循环"""
        while self._running:
            try:
                await asyncio.sleep(self._config.adjust_interval)
                self._adjuster.adjust_config(self._config, self._stats)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Adjust loop error: {e}")
                await asyncio.sleep(DISPATCH_LOOP_INTERVAL)