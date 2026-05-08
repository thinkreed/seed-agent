"""LifecycleMessageBus 核心实现

基于 Qwen-Code MessageBus 设计的请求/响应模式消息总线：
- 支持 AbortSignal 取消
- 超时管理
- 多钩子结果合并
"""

import asyncio
import logging
import uuid
from typing import Any

from src.tools import PermissionDecision

from ._aggregator import HookAggregator
from ._message_bus_abort import (
    cleanup_abort_listener,
    schedule_cancel_task,
    setup_abort_listener,
)
from ._message_bus_types import PendingRequest

logger = logging.getLogger(__name__)


class LifecycleMessageBus:
    """生命周期钩子消息总线

    提供 request/response 模式，支持 AbortSignal 取消和超时管理。
    """

    def __init__(self) -> None:
        self._pending_requests: dict[str, PendingRequest] = {}
        self._handlers: dict[str, list[Any]] = {}
        self._lock = asyncio.Lock()

    def register_handler(self, request_type: str, handler: Any) -> None:
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

        cancel_callback = setup_abort_listener(
            correlation_id, abort_signal, self._cancel_request
        )
        full_request = {**payload, "correlation_id": correlation_id, "request_type": request_type}
        await self._dispatch_request(request_type, full_request)

        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000)
        except TimeoutError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise TimeoutError(f"Request timeout: {request_type}")
        except asyncio.CancelledError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise
        finally:
            cleanup_abort_listener(abort_signal, cancel_callback)

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
        results = await self._execute_handlers(handlers, request)
        aggregated = HookAggregator.aggregate_results(results)
        await self.respond(request["correlation_id"], aggregated)

    async def _execute_handlers(
        self, handlers: list[Any], request: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """执行所有处理器并收集结果"""
        results = []
        for handler in handlers:
            try:
                result = await handler(request) if asyncio.iscoroutinefunction(handler) else handler(request)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Handler error: {e}")
                results.append({"decision": PermissionDecision.Deny.value, "reason": f"Handler error: {e}"})
        return results

    def _cancel_request(self, correlation_id: str) -> None:
        """取消等待中的请求"""
        schedule_cancel_task(self._lock, self._pending_requests, correlation_id)

    def get_pending_count(self) -> int:
        """获取等待中的请求数量"""
        return len(self._pending_requests)

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()


__all__ = ["LifecycleMessageBus"]