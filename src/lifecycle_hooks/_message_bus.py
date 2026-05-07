"""
Lifecycle Hooks MessageBus

基于 Qwen-Code MessageBus 设计的请求/响应模式消息总线：
- 支持 AbortSignal 取消
- 超时管理
- 多钩子结果合并

重构说明:
- PermissionDecision 从 src/tools/_types.py 导入（避免重复）
- PendingRequest 移至 _types.py
- HookAggregator 移至 _aggregator.py
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Any

from src.tools import PermissionDecision

from ._aggregator import HookAggregator
from ._types import PendingRequest

logger = logging.getLogger(__name__)


class LifecycleMessageBus:
    """生命周期钩子消息总线

    提供 request/response 模式：
    - 发送请求并等待响应
    - 支持 AbortSignal 取消等待
    - 超时管理

    使用示例:
        bus = LifecycleMessageBus()

        # 注册响应处理器
        bus.register_handler("tool_permission", handle_permission_response)

        # 发送请求并等待响应
        result = await bus.request(
            "tool_permission",
            {"tool_name": "bash", "args": {"command": "rm -rf"}},
            timeout_ms=30000
        )
    """

    def __init__(self) -> None:
        self._pending_requests: dict[str, PendingRequest] = {}
        self._handlers: dict[str, list[Callable]] = {}
        self._lock = asyncio.Lock()

    def register_handler(
        self, request_type: str, handler: Callable[[dict[str, Any]], Any]
    ) -> None:
        """注册响应处理器"""
        if request_type not in self._handlers:
            self._handlers[request_type] = []
        self._handlers[request_type].append(handler)
        logger.debug(f"Handler registered: type={request_type}")

    async def request(
        self,
        request_type: str,
        payload: dict[str, Any],
        timeout_ms: int = 60000,
        abort_signal: Any | None = None,
    ) -> dict[str, Any]:
        """发送请求并等待响应"""
        correlation_id = str(uuid.uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()

        pending = PendingRequest(
            correlation_id=correlation_id,
            request_type=request_type,
            future=future,
            timeout_ms=timeout_ms,
        )

        async with self._lock:
            self._pending_requests[correlation_id] = pending

        # AbortSignal 监听器
        cancel_callback = None
        if abort_signal is not None:
            cancel_callback = lambda: self._cancel_request(correlation_id)
            if hasattr(abort_signal, "add_listener"):
                abort_signal.add_listener(cancel_callback)
            elif hasattr(abort_signal, "add_done_callback"):
                abort_signal.add_done_callback(cancel_callback)

        full_request = {
            **payload,
            "correlation_id": correlation_id,
            "request_type": request_type,
        }
        await self._dispatch_request(request_type, full_request)

        try:
            result = await asyncio.wait_for(future, timeout=timeout_ms / 1000)
            return result
        except TimeoutError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise TimeoutError(f"Request timeout: {request_type}")
        except asyncio.CancelledError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise
        finally:
            if cancel_callback and abort_signal is not None:
                if hasattr(abort_signal, "remove_listener"):
                    abort_signal.remove_listener(cancel_callback)

    async def respond(self, correlation_id: str, response: dict[str, Any]) -> bool:
        """发送响应"""
        async with self._lock:
            pending = self._pending_requests.pop(correlation_id, None)

        if pending is None:
            logger.warning(f"Request not found: {correlation_id}")
            return False

        if not pending.future.done():
            pending.future.set_result(response)
            logger.debug(f"Response sent: {correlation_id}")
            return True
        return False

    async def _dispatch_request(self, request_type: str, request: dict[str, Any]) -> None:
        """分发请求到处理器"""
        handlers = self._handlers.get(request_type, [])

        if not handlers:
            await self.respond(
                request["correlation_id"],
                {"decision": PermissionDecision.Allow.value, "handled": False},
            )
            return

        results = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(request)
                else:
                    result = handler(request)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Handler error: {e}")
                results.append({
                    "decision": PermissionDecision.Deny.value,
                    "reason": f"Handler error: {e}",
                })

        aggregated = HookAggregator.aggregate_results(results)
        await self.respond(request["correlation_id"], aggregated)

    def _cancel_request(self, correlation_id: str) -> None:
        """取消等待中的请求"""
        async def _cancel():
            async with self._lock:
                pending = self._pending_requests.pop(correlation_id, None)
                if pending and not pending.future.done():
                    pending.future.cancel()

        try:
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.create_task(_cancel())
            )
        except RuntimeError:
            pass

    def get_pending_count(self) -> int:
        """获取等待中的请求数量"""
        return len(self._pending_requests)

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()


# 全局单例
_global_message_bus: LifecycleMessageBus | None = None


def get_message_bus() -> LifecycleMessageBus:
    """获取全局消息总线"""
    global _global_message_bus
    if _global_message_bus is None:
        _global_message_bus = LifecycleMessageBus()
    return _global_message_bus


def reset_message_bus() -> None:
    """重置全局消息总线"""
    global _global_message_bus
    _global_message_bus = None


__all__ = [
    "HookAggregator",
    "LifecycleMessageBus",
    "PendingRequest",
    "get_message_bus",
    "reset_message_bus",
]