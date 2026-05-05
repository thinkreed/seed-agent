"""CancellationToken 模块 - 细粒度取消控制

支持：
- 多级取消（父令牌取消时子令牌也取消）
- 超时取消
- 组合取消（任一令牌取消即取消）
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CancellationToken:
    """取消令牌 - 更细粒度的取消控制

    使用方式：
        parent = CancellationToken()
        child = CancellationToken(parent=parent)

        parent.cancel()  # 同时取消 parent 和 child
    """

    _cancelled: bool = False
    reason: str = ""
    parent: CancellationToken | None = None
    _children: list[CancellationToken] = field(default_factory=list)

    def __post_init__(self) -> None:
        """初始化后注册到父令牌"""
        if self.parent:
            self.parent._children.append(self)
            if self.parent._cancelled:
                self._cancelled = True
                self.reason = self.parent.reason

    @property
    def cancelled(self) -> bool:
        """是否已取消"""
        if self._cancelled:
            return True
        if self.parent and self.parent.cancelled:
            self._cancelled = True
            self.reason = self.parent.reason
            return True
        return False

    def cancel(self, reason: str = "") -> None:
        """取消此令牌及其所有子令牌"""
        if self._cancelled:
            return

        self._cancelled = True
        self.reason = reason
        logger.debug(f"CancellationToken cancelled: reason={reason}")

        for child in self._children:
            child.cancel(reason=f"parent_cancelled: {reason}")

    def create_child(self) -> CancellationToken:
        """创建子令牌"""
        return CancellationToken(parent=self)

    def check(self) -> None:
        """检查取消状态"""
        if self.cancelled:
            raise asyncio.CancelledError(self.reason)


class TimeoutCancellationToken(CancellationToken):
    """超时取消令牌

    在指定时间后自动取消

    使用方式：
        token = TimeoutCancellationToken(timeout_seconds=30)
        token.start_timeout()  # 启动计时器
    """

    def __init__(
        self,
        timeout_seconds: float,
        parent: CancellationToken | None = None,
        reason: str = "timeout",
    ):
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
            pass  # 计时器被取消

    def cancel(self, reason: str = "") -> None:
        """取消令牌并停止计时器"""
        super().cancel(reason=reason)
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
        super().__init__()
        self._sources = sources
        self._composite_reason = reason

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