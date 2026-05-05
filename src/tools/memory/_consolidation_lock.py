"""
记忆整合锁机制

防止多进程并发执行 autodream 记忆整合：
- 文件锁原子操作（flag: 'wx'）
- 锁过期自动清理（防止死锁）
- PID 记录用于诊断

参考: Qwen-Code 整合锁设计
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("seed_agent")

# 锁过期时间（1 小时）
LOCK_STALE_MS = 60 * 60 * 1000


class ConsolidationLock:
    """记忆整合锁

    使用文件锁防止多进程并发执行记忆整合：
    - 锁文件包含 PID 用于诊断
    - 锁过期自动清理（防止进程崩溃后死锁）
    - 原子创建（flag: 'wx'）确保独占

    Usage:
        lock = ConsolidationLock(lock_path)
        if lock.acquire():
            try:
                # 执行记忆整合
                await consolidate_memories()
            finally:
                lock.release()
        else:
            logger.info("Another process is consolidating memories")
    """

    def __init__(self, lock_path: Optional[Path] = None) -> None:
        """初始化整合锁

        Args:
            lock_path: 锁文件路径，默认为 ~/.seed/consolidation.lock
        """
        if lock_path is None:
            # 默认路径
            home = Path.home()
            seed_dir = home / ".seed"
            seed_dir.mkdir(parents=True, exist_ok=True)
            lock_path = seed_dir / "consolidation.lock"

        self._lock_path = lock_path
        self._lock_dir = lock_path.parent
        self._held = False

    def acquire(self) -> bool:
        """尝试获取锁

        Returns:
            True 如果成功获取锁，False 如果锁被其他进程持有
        """
        # 确保目录存在
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        # 检查是否存在过期锁
        if self._lock_path.exists():
            if self._is_stale_lock():
                logger.warning("Found stale consolidation lock, cleaning up")
                self._force_release()
            else:
                # 锁被其他进程持有
                holder_pid = self._read_lock_pid()
                logger.info(f"Consolidation lock held by process {holder_pid}")
                return False

        # 尝试原子创建锁文件
        try:
            with open(self._lock_path, "x", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            self._held = True
            logger.debug(f"Acquired consolidation lock (PID: {os.getpid()})")
            return True
        except FileExistsError:
            # 另一个进程刚刚创建了锁
            logger.info("Failed to acquire consolidation lock (race condition)")
            return False
        except OSError as e:
            logger.error(f"Failed to create lock file: {e}")
            return False

    def release(self) -> None:
        """释放锁"""
        if not self._held:
            return

        try:
            self._lock_path.unlink(missing_ok=True)
            self._held = False
            logger.debug(f"Released consolidation lock (PID: {os.getpid()})")
        except OSError as e:
            logger.error(f"Failed to release lock file: {e}")
            self._held = False

    def _is_stale_lock(self) -> bool:
        """检查锁是否过期

        Returns:
            True 如果锁创建时间超过 LOCK_STALE_MS
        """
        try:
            stat = self._lock_path.stat()
            mtime_ms = stat.st_mtime * 1000
            now_ms = time.time() * 1000
            return (now_ms - mtime_ms) > LOCK_STALE_MS
        except OSError:
            return False

    def _force_release(self) -> None:
        """强制释放锁（用于清理过期锁）"""
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Failed to force release lock: {e}")

    def _read_lock_pid(self) -> Optional[int]:
        """读取锁文件中记录的 PID"""
        try:
            content = self._lock_path.read_text(encoding="utf-8").strip()
            return int(content)
        except (OSError, ValueError):
            return None

    def is_held(self) -> bool:
        """检查锁是否被持有"""
        return self._held

    def get_lock_path(self) -> Path:
        """获取锁文件路径"""
        return self._lock_path


def acquire_dream_lock(project_root: Optional[Path] = None) -> ConsolidationLock:
    """获取记忆整合锁的便捷函数

    Args:
        project_root: 项目根目录，用于确定锁路径

    Returns:
        ConsolidationLock 实例，调用者需检查 acquire() 结果

    Example:
        lock = acquire_dream_lock()
        if lock.acquire():
            try:
                await consolidate_memories()
            finally:
                lock.release()
    """
    if project_root is not None:
        # 项目级锁
        lock_path = project_root / ".seed" / "consolidation.lock"
    else:
        lock_path = None

    return ConsolidationLock(lock_path)


__all__ = [
    "ConsolidationLock",
    "acquire_dream_lock",
    "LOCK_STALE_MS",
]