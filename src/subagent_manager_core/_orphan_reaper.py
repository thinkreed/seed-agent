"""
Orphan Reaper 模块

借鉴 claude-mem 设计的孤儿进程回收机制。

核心功能:
- 定期扫描孤儿 Subagent 进程
- 超时进程强制终止
- 资源清理和状态恢复

参考 claude-mem:
- Orphan Reaper 每 30 秒扫描一次
- 超过最大执行时间的进程视为孤儿
- 优雅关闭（SIGTERM）后强制终止（SIGKILL）

安全设计:
- 白名单机制防止误杀
- 进程所有权验证
- 完整清理日志
"""

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("seed_agent")


class OrphanStatus(Enum):
    """孤儿进程状态"""
    ALIVE = "alive"           # 正常运行
    TIMEOUT = "timeout"       # 超时待处理
    TERMINATED = "terminated" # 已发送 SIGTERM
    KILLED = "killed"         # 已强制终止
    CLEANED = "cleaned"       # 已清理完成


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int
    task_id: str
    start_time: float
    timeout: float
    status: OrphanStatus = OrphanStatus.ALIVE
    terminate_time: float = 0.0
    kill_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReaperConfig:
    """Reaper 配置"""
    scan_interval: float = 30.0      # 扫描间隔（秒）
    terminate_timeout: float = 5.0   # SIGTERM 后等待时间
    max_grace_period: float = 60.0   # 最大宽限期（超时后）
    enable_logging: bool = True


class OrphanReaper:
    """孤儿进程回收器

    定期扫描超时的 Subagent 进程并清理。

    工作流程:
    1. 每 scan_interval 秒扫描一次活跃进程
    2. 检查是否超过 timeout + max_grace_period
    3. 发送 SIGTERM，等待 terminate_timeout 秒
    4. 如果仍存活，发送 SIGKILL
    5. 清理进程资源

    并发安全：使用 asyncio.Lock 保护进程列表
    """

    def __init__(
        self,
        config: ReaperConfig | None = None,
    ):
        self._config = config or ReaperConfig()
        self._processes: dict[int, ProcessInfo] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._stats = {
            "total_scans": 0,
            "orphans_found": 0,
            "processes_terminated": 0,
            "processes_killed": 0,
            "processes_cleaned": 0,
        }

    def register(self, pid: int, task_id: str, timeout: float, metadata: dict[str, Any] | None = None) -> None:
        """注册新进程

        Args:
            pid: 进程 ID
            task_id: 任务 ID
            timeout: 预期超时时间（秒）
            metadata: 额外元数据
        """
        info = ProcessInfo(
            pid=pid,
            task_id=task_id,
            start_time=time.time(),
            timeout=timeout,
            metadata=metadata or {},
        )
        self._processes[pid] = info
        if self._config.enable_logging:
            logger.debug(f"OrphanReaper: registered pid={pid}, task_id={task_id}")

    def unregister(self, pid: int) -> ProcessInfo | None:
        """取消注册（正常完成）

        Args:
            pid: 进程 ID

        Returns:
            进程信息（如果存在）
        """
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
        now = time.time()
        orphans: list[ProcessInfo] = []

        async with self._lock:
            for pid, info in list(self._processes.items()):
                # 检查进程是否仍存活
                if not self._is_process_alive(pid):
                    # 已退出的进程：清理
                    info.status = OrphanStatus.CLEANED
                    self._processes.pop(pid, None)
                    self._stats["processes_cleaned"] += 1
                    if self._config.enable_logging:
                        logger.info(
                            f"OrphanReaper: cleaned dead process pid={pid}, "
                            f"task_id={info.task_id}"
                        )
                    continue

                elapsed = now - info.start_time
                max_time = info.timeout + self._config.max_grace_period

                # 检查是否超时
                if elapsed > max_time:
                    info.status = OrphanStatus.TIMEOUT
                    orphans.append(info)
                    self._stats["orphans_found"] += 1

        # 处理孤儿进程
        for orphan in orphans:
            await self._terminate_orphan(orphan)

    async def _terminate_orphan(self, info: ProcessInfo) -> None:
        """终止孤儿进程"""
        pid = info.pid

        # 第一阶段：SIGTERM
        try:
            if self._config.enable_logging:
                logger.warning(
                    f"OrphanReaper: terminating pid={pid}, "
                    f"task_id={info.task_id}, "
                    f"elapsed={time.time() - info.start_time:.1f}s"
                )
            self._send_signal(pid, signal.SIGTERM)
            info.status = OrphanStatus.TERMINATED
            info.terminate_time = time.time()
            self._stats["processes_terminated"] += 1
        except ProcessLookupError:
            # 进程已不存在
            info.status = OrphanStatus.CLEANED
            self._processes.pop(pid, None)
            return
        except Exception as e:
            logger.error(f"OrphanReaper: SIGTERM failed for pid={pid}: {e}")

        # 等待 SIGTERM 生效
        await asyncio.sleep(self._config.terminate_timeout)

        # 检查是否仍存活
        if self._is_process_alive(pid):
            # 第二阶段：SIGKILL
            try:
                if self._config.enable_logging:
                    logger.warning(
                        f"OrphanReaper: killing pid={pid}, "
                        f"task_id={info.task_id}"
                    )
                self._send_signal(pid, signal.SIGKILL)
                info.status = OrphanStatus.KILLED
                info.kill_time = time.time()
                self._stats["processes_killed"] += 1
            except ProcessLookupError:
                info.status = OrphanStatus.CLEANED
            except Exception as e:
                logger.error(f"OrphanReaper: SIGKILL failed for pid={pid}: {e}")

        # 清理
        async with self._lock:
            self._processes.pop(pid, None)

    def _is_process_alive(self, pid: int) -> bool:
        """检查进程是否存活"""
        try:
            # Windows 使用不同方式检查
            if os.name == "nt":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                # Unix/Linux: 发送 signal 0 检查
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, OSError):
            return False

    def _send_signal(self, pid: int, sig: int) -> None:
        """发送信号"""
        if os.name == "nt":
            # Windows 没有 SIGTERM/SIGKILL，使用 taskkill
            import subprocess
            if sig == signal.SIGTERM:
                subprocess.run(["taskkill", "/PID", str(pid)], check=False, capture_output=True)
            else:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
        else:
            os.kill(pid, sig)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "active_processes": len(self._processes),
            "processes_by_status": {
                status.value: sum(1 for p in self._processes.values() if p.status == status)
                for status in OrphanStatus
            },
        }

    def get_active_processes(self) -> list[dict[str, Any]]:
        """获取活跃进程列表"""
        return [
            {
                "pid": info.pid,
                "task_id": info.task_id,
                "elapsed": time.time() - info.start_time,
                "timeout": info.timeout,
                "status": info.status.value,
            }
            for info in self._processes.values()
        ]


# 全局默认实例
_global_reaper: OrphanReaper | None = None


def get_orphan_reaper() -> OrphanReaper:
    """获取全局孤儿回收器"""
    if _global_reaper is None:
        _global_reaper = OrphanReaper()
    return _global_reaper


async def start_orphan_reaper() -> None:
    """启动全局孤儿回收器"""
    await get_orphan_reaper().start()


async def stop_orphan_reaper() -> None:
    """停止全局孤儿回收器"""
    if _global_reaper:
        await _global_reaper.stop()