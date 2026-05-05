"""AbortSignal 模块 - 基础取消信号

基于 qwen-code 的 AbortController Pattern 设计：
- 每个任务关联一个 AbortController
- 取消时调用 abort() 发送信号
- 各执行点检查 signal.aborted 状态

参考：
- qwen-code: background-tasks.ts, acpAgent.ts
- JavaScript AbortController API
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

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
        """添加取消监听器"""
        with self._lock:
            if self.aborted:
                logger.warning("Cannot add listener to already aborted signal")
                return
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[AbortSignal], None]) -> None:
        """移除取消监听器"""
        with self._lock:
            try:
                self._listeners.remove(listener)
            except ValueError:
                logger.warning("Listener not found in signal")

    def check(self) -> None:
        """检查取消状态，如已取消则抛出 CancelledError"""
        if self.aborted:
            raise asyncio.CancelledError(self.reason)


class AbortController:
    """取消控制器

    使用方式：
        controller = AbortController()
        signal = controller.signal

        if signal.aborted:
            return "cancelled"

        controller.abort("user_cancelled")
    """

    def __init__(self) -> None:
        self.signal = AbortSignal()

    def abort(self, reason: str = "") -> None:
        """取消关联的任务"""
        self.signal.abort(reason)