"""AbortSignal 处理逻辑

提供取消信号监听器的设置和清理功能。
"""

import asyncio
from typing import Any


def setup_abort_listener(
    correlation_id: str,
    abort_signal: Any | None,
    cancel_fn: Any,
) -> Any:
    """设置取消信号监听器

    Args:
        correlation_id: 请求关联 ID
        abort_signal: 取消信号对象
        cancel_fn: 取消回调函数（接受 correlation_id 参数）

    Returns:
        注册的回调函数，用于后续清理
    """
    if abort_signal is None:
        return None

    def cancel_callback() -> None:
        cancel_fn(correlation_id)

    if hasattr(abort_signal, "add_listener"):
        abort_signal.add_listener(cancel_callback)
    elif hasattr(abort_signal, "add_done_callback"):
        abort_signal.add_done_callback(cancel_callback)
    return cancel_callback


def cleanup_abort_listener(abort_signal: Any | None, cancel_callback: Any) -> None:
    """清理取消信号监听器

    Args:
        abort_signal: 取消信号对象
        cancel_callback: 注册的回调函数
    """
    if cancel_callback and abort_signal is not None:
        if hasattr(abort_signal, "remove_listener"):
            abort_signal.remove_listener(cancel_callback)


async def cancel_pending_request(
    lock: asyncio.Lock,
    pending_requests: dict[str, Any],
    correlation_id: str,
) -> None:
    """取消等待中的请求

    Args:
        lock: 异步锁
        pending_requests: 等待中的请求字典
        correlation_id: 请求关联 ID
    """
    async with lock:
        pending = pending_requests.pop(correlation_id, None)
        if pending and not pending.future.done():
            pending.future.cancel()


def schedule_cancel_task(
    lock: asyncio.Lock,
    pending_requests: dict[str, Any],
    correlation_id: str,
) -> None:
    """调度取消任务（线程安全）

    Args:
        lock: 异步锁
        pending_requests: 等待中的请求字典
        correlation_id: 请求关联 ID
    """
    try:
        asyncio.get_event_loop().call_soon_threadsafe(
            lambda: asyncio.create_task(
                cancel_pending_request(lock, pending_requests, correlation_id)
            )
        )
    except RuntimeError:
        pass


__all__ = [
    "cancel_pending_request",
    "cleanup_abort_listener",
    "schedule_cancel_task",
    "setup_abort_listener",
]