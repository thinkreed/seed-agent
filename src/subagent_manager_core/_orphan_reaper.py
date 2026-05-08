"""
Orphan Reaper 模块

借鉴 claude-mem 设计的孤儿进程回收机制。
"""

import asyncio
import logging
import signal
import time
from typing import Any

from ._orphan_process import is_process_alive, send_signal
from ._orphan_types import OrphanStatus, ProcessInfo, ReaperConfig

logger = logging.getLogger("seed_agent")


class OrphanReaper:
    """孤儿进程回收器：定期扫描超时的 Subagent 进程并清理"""

    def __init__(self, config: ReaperConfig | None = None):
        self._config = config or ReaperConfig()
        self._processes: dict[int, ProcessInfo] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stats = {"total_scans": 0, "orphans_found": 0, "processes_terminated": 0, "processes_killed": 0, "processes_cleaned": 0}

    def register(self, pid: int, task_id: str, timeout: float, metadata: dict[str, Any] | None = None) -> None:
        """注册新进程"""
        info = ProcessInfo(pid=pid, task_id=task_id, start_time=time.time(), timeout=timeout, metadata=metadata or {})
        self._processes[pid] = info
        if self._config.enable_logging:
            logger.debug(f"OrphanReaper: registered pid={pid}, task_id={task_id}")

    def unregister(self, pid: int) -> ProcessInfo | None:
        """取消注册（正常完成）"""
        info = self._processes.pop(pid, None)
        if info and self._config.enable_logging:
            logger.debug(f"OrphanReaper: unregistered pid={pid}, task_id={info.task_id}")
        return info

    async def start(self) -> None:
        """启动 Reaper 后台任务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reaper_loop())
        if self._config.enable_logging:
            logger.info("OrphanReaper started")

    async def stop(self) -> None:
        """停止 Reaper"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._config.enable_logging:
            logger.info("OrphanReaper stopped")

    async def _reaper_loop(self) -> None:
        """Reaper 主循环"""
        while self._running:
            try:
                await self._scan_and_reap()
                self._stats["total_scans"] += 1
            except Exception as e:
                logger.error(f"OrphanReaper scan error: {e}")
            await asyncio.sleep(self._config.scan_interval)

    async def _scan_and_reap(self) -> None:
        """扫描并回收孤儿进程"""
        now, orphans = time.time(), []
        async with self._lock:
            for pid, info in list(self._processes.items()):
                if not is_process_alive(pid):
                    info.status, self._processes[pid] = OrphanStatus.CLEANED, None  # type: ignore
                    self._processes.pop(pid, None)
                    self._stats["processes_cleaned"] += 1
                    if self._config.enable_logging:
                        logger.info(f"OrphanReaper: cleaned dead process pid={pid}")
                    continue
                if (now - info.start_time) > (info.timeout + self._config.max_grace_period):
                    info.status = OrphanStatus.TIMEOUT
                    orphans.append(info)
                    self._stats["orphans_found"] += 1
        for orphan in orphans:
            await self._terminate_orphan(orphan)

    async def _terminate_orphan(self, info: ProcessInfo) -> None:
        """终止孤儿进程（SIGTERM -> SIGKILL）"""
        pid = info.pid
        try:
            if self._config.enable_logging:
                logger.warning(f"OrphanReaper: terminating pid={pid}, task_id={info.task_id}")
            send_signal(pid, signal.SIGTERM)
            info.status, info.terminate_time = OrphanStatus.TERMINATED, time.time()
            self._stats["processes_terminated"] += 1
        except ProcessLookupError:
            info.status = OrphanStatus.CLEANED
            self._processes.pop(pid, None)
            return
        except Exception as e:
            logger.error(f"OrphanReaper: SIGTERM failed for pid={pid}: {e}")

        await asyncio.sleep(self._config.terminate_timeout)
        if is_process_alive(pid):
            try:
                if self._config.enable_logging:
                    logger.warning(f"OrphanReaper: killing pid={pid}")
                send_signal(pid, signal.SIGKILL)
                info.status, info.kill_time = OrphanStatus.KILLED, time.time()
                self._stats["processes_killed"] += 1
            except ProcessLookupError:
                info.status = OrphanStatus.CLEANED
            except Exception as e:
                logger.error(f"OrphanReaper: SIGKILL failed for pid={pid}: {e}")
        async with self._lock:
            self._processes.pop(pid, None)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {**self._stats, "active_processes": len(self._processes),
                "processes_by_status": {s.value: sum(1 for p in self._processes.values() if p.status == s) for s in OrphanStatus}}

    def get_active_processes(self) -> list[dict[str, Any]]:
        """获取活跃进程列表"""
        return [{"pid": i.pid, "task_id": i.task_id, "elapsed": time.time() - i.start_time, "timeout": i.timeout, "status": i.status.value} for i in self._processes.values()]


# 重新导出全局辅助函数，保持 API 兼容
from ._orphan_api import get_orphan_reaper, start_orphan_reaper, stop_orphan_reaper  # noqa: E402

__all__ = ["OrphanReaper", "OrphanStatus", "ProcessInfo", "ReaperConfig", "get_orphan_reaper", "start_orphan_reaper", "stop_orphan_reaper"]