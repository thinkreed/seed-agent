"""
AbortSignal 模块 - 取消信号控制

基于 qwen-code 的 AbortController Pattern 设计：
- 每个任务关联一个 AbortController
- 取消时调用 abort() 发送信号
- 各执行点检查 signal.aborted 状态
- 优雅期让自然完成优先

核心特性：
- 异步取消信号传播
- 监听器机制支持多订阅者
- 原因追踪便于调试

参考：
- qwen-code: background-tasks.ts, acpAgent.ts
- JavaScript AbortController API
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AbortSignal:
    """取消信号（类似 JavaScript AbortSignal）

    核心设计：
    - aborted: 是否已取消
    - reason: 取消原因
    - listeners: 取消监听器列表（线程安全）

    使用方式：
        signal = AbortSignal()
        if signal.aborted:
            return "cancelled"

        signal.add_listener(on_cancel_callback)
    """

    aborted: bool = False
    reason: str = ""
    _listeners: list[Callable[[AbortSignal], None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def abort(self, reason: str = "") -> None:
        """触发取消

        Args:
            reason: 取消原因

        触发后：
        - 设置 aborted = True
        - 记录 reason
        - 调用所有监听器
        - 清空监听器列表
        """
        with self._lock:
            if self.aborted:
                return  # 已取消，不重复触发

            self.aborted = True
            self.reason = reason

            # 复制监听器列表，避免在调用时被修改
            listeners = list(self._listeners)
            self._listeners.clear()

        logger.info(f"AbortSignal triggered: reason={reason}")

        # 在锁外触发监听器（避免死锁）
        for listener in listeners:
            try:
                listener(self)
            except Exception as e:
                logger.warning(f"AbortSignal listener error: {type(e).__name__}: {e}")

    def add_listener(self, listener: Callable[[AbortSignal], None]) -> None:
        """添加取消监听器

        Args:
            listener: 取消时调用的回调函数

        注意：
        - 取消触发后监听器会被清空
        - 已取消状态下添加监听器不会被执行
        """
        with self._lock:
            if self.aborted:
                logger.warning("Cannot add listener to already aborted signal")
                return

            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[AbortSignal], None]) -> None:
        """移除取消监听器

        Args:
            listener: 要移除的监听器
        """
        with self._lock:
            try:
                self._listeners.remove(listener)
            except ValueError:
                logger.warning("Listener not found in signal")

    def check(self) -> None:
        """检查取消状态，如已取消则抛出 CancelledError

        Raises:
            asyncio.CancelledError: 如果已取消
        """
        if self.aborted:
            raise asyncio.CancelledError(self.reason)


class AbortController:
    """取消控制器

    核心设计：
    - signal: 关联的取消信号
    - abort(): 触发取消

    使用方式：
        controller = AbortController()
        signal = controller.signal

        # 在执行点检查
        if signal.aborted:
            return "cancelled"

        # 触发取消
        controller.abort("user_cancelled")
    """

    def __init__(self):
        """初始化控制器"""
        self.signal = AbortSignal()

    def abort(self, reason: str = "") -> None:
        """取消关联的任务

        Args:
            reason: 取消原因
        """
        self.signal.abort(reason)


@dataclass
class CancellationToken:
    """取消令牌 - 更细粒度的取消控制

    支持：
    - 多级取消（父令牌取消时子令牌也取消）
    - 超时取消
    - 组合取消（任一令牌取消即取消）

    使用方式：
        parent = CancellationToken()
        child = CancellationToken(parent=parent)

        parent.cancel()  # 同时取消 parent 和 child
    """

    _cancelled: bool = False
    reason: str = ""
    parent: CancellationToken | None = None
    _children: list[CancellationToken] = field(default_factory=list)

    def __post_init__(self):
        """初始化后注册到父令牌"""
        if self.parent:
            self.parent._children.append(self)
            # 如果父令牌已取消，立即取消子令牌
            if self.parent._cancelled:
                self._cancelled = True
                self.reason = self.parent.reason

    @property
    def cancelled(self) -> bool:
        """是否已取消"""
        # 检查自身和父令牌
        if self._cancelled:
            return True
        if self.parent and self.parent.cancelled:
            self._cancelled = True
            self.reason = self.parent.reason
            return True
        return False

    def cancel(self, reason: str = "") -> None:
        """取消此令牌及其所有子令牌

        Args:
            reason: 取消原因
        """
        if self._cancelled:
            return

        self._cancelled = True
        self.reason = reason

        logger.debug(f"CancellationToken cancelled: reason={reason}")

        # 取消所有子令牌
        for child in self._children:
            child.cancel(reason=f"parent_cancelled: {reason}")

    def create_child(self) -> CancellationToken:
        """创建子令牌

        Returns:
            子令牌（父令牌取消时自动取消）
        """
        return CancellationToken(parent=self)

    def check(self) -> None:
        """检查取消状态

        Raises:
            asyncio.CancelledError: 如果已取消
        """
        if self.cancelled:
            raise asyncio.CancelledError(self.reason)


class TimeoutCancellationToken(CancellationToken):
    """超时取消令牌

    在指定时间后自动取消

    使用方式：
        token = TimeoutCancellationToken(timeout_seconds=30)
        # 30秒后自动取消
    """

    def __init__(
        self,
        timeout_seconds: float,
        parent: CancellationToken | None = None,
        reason: str = "timeout",
    ):
        """初始化超时令牌

        Args:
            timeout_seconds: 超时秒数
            parent: 父令牌（可选）
            reason: 超时原因
        """
        super().__init__(parent=parent)
        self._timeout_seconds = timeout_seconds
        self._timeout_reason = reason
        self._timeout_task: asyncio.Task | None = None

    def start_timeout(self) -> None:
        """启动超时计时器"""
        if self._timeout_task is None:
            self._timeout_task = asyncio.create_task(self._timeout_handler())

    async def _timeout_handler(self) -> None:
        """超时处理"""
        try:
            await asyncio.sleep(self._timeout_seconds)
            if not self.cancelled:
                self.cancel(reason=self._timeout_reason)
        except asyncio.CancelledError:
            # 计时器被取消，正常情况
            pass

    def cancel(self, reason: str = "") -> None:
        """取消令牌并停止计时器"""
        super().cancel(reason=reason)

        # 停止计时器
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None


class CompositeCancellationToken(CancellationToken):
    """组合取消令牌

    任一源令牌取消即取消

    使用方式：
        token1 = CancellationToken()
        token2 = CancellationToken()
        composite = CompositeCancellationToken([token1, token2])

        token1.cancel()  # composite 也取消
    """

    def __init__(
        self, sources: list[CancellationToken], reason: str = "composite_cancelled"
    ):
        """初始化组合令牌

        Args:
            sources: 源令牌列表
            reason: 取消原因
        """
        super().__init__()
        self._sources = sources
        self._composite_reason = reason

        # 注册监听器
        for source in sources:
            source._children.append(self)

    @property
    def cancelled(self) -> bool:
        """检查任一源令牌是否取消"""
        if self._cancelled:
            return True

        for source in self._sources:
            if source.cancelled:
                self._cancelled = True
                self.reason = f"{self._composite_reason}: source_cancelled"
                return True

        return False


def create_linked_token(
    parent: CancellationToken | None = None, timeout: float | None = None
) -> CancellationToken:
    """创建关联令牌（便捷函数）

    Args:
        parent: 父令牌（可选）
        timeout: 超时秒数（可选）

    Returns:
        配置好的取消令牌
    """
    if timeout is not None:
        token = TimeoutCancellationToken(timeout, parent=parent)
        token.start_timeout()
        return token

    return CancellationToken(parent=parent)
