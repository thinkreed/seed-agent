"""空闲监控模块

提供空闲时间监控和活动记录功能:
- record_activity: 记录用户活动时间
- get_idle_time: 获取当前空闲时间
- _idle_monitor_loop: 空闲监控主循环

从 AutonomousExplorer 中提取，保持接口不变。
"""

import asyncio
import contextlib
import logging
import time

logger = logging.getLogger("seed_agent")


class IdleMonitor:
    """空闲监控器

    监控用户活动时间，在空闲超时后触发自主探索。

    Attributes:
        _last_activity: 上次活动时间戳
        _running: 监控是否运行中
        _task: 监控任务
        _idle_timeout: 空闲超时时间（秒）
    """

    def __init__(self, idle_timeout: float):
        """初始化空闲监控器

        Args:
            idle_timeout: 空闲超时时间（秒）
        """
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._idle_timeout: float = idle_timeout

    def record_activity(self) -> None:
        """记录用户活动时间"""
        self._last_activity = time.time()

    def get_idle_time(self) -> float:
        """获取当前空闲时间（秒）

        Returns:
            从上次活动到现在的时间间隔（秒）
        """
        return time.time() - self._last_activity

    async def start(self) -> None:
        """启动空闲监控"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._idle_monitor_loop())
        logger.warning("Autonomous explorer started")

    async def stop(self) -> None:
        """停止空闲监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.warning("Autonomous explorer stopped")

    async def _idle_monitor_loop(
        self,
        on_idle_triggered: "asyncio.coroutine",
    ) -> None:
        """空闲监控循环

        Args:
            on_idle_triggered: 空闲触发时的回调协程
        """
        while self._running:
            idle_time = self.get_idle_time()

            if idle_time >= self._idle_timeout:
                logger.warning(
                    f"Idle for {idle_time / 60:.1f} minutes, "
                    "starting autonomous exploration"
                )
                result = await on_idle_triggered()
                if result:
                    self.record_activity()  # 仅成功时重置计时
                else:
                    logger.warning(
                        "Autonomous exploration failed, not resetting idle timer"
                    )

            # 每30秒检查一次
            await asyncio.sleep(30)