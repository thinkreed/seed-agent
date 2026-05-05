"""
Lifecycle Hooks MessageBus

基于 Qwen-Code MessageBus 设计的请求/响应模式消息总线：
- 支持 AbortSignal 取消
- 超时管理
- 多钩子结果合并

核心特性：
- request/response 模式：发送请求并等待响应
- AbortSignal 支持：取消等待中的请求
- HookAggregator：合并多个钩子的结果

版本: v1.0 (Wiki 知识落地)
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PermissionDecision(Enum):
    """权限决策枚举（与 tools/__init__.py 保持一致）"""

    Allow = "allow"
    Ask = "ask"
    Deny = "deny"


@dataclass
class PendingRequest:
    """等待中的请求"""

    correlation_id: str
    request_type: str
    future: asyncio.Future
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    timeout_ms: int = 60000


class HookAggregator:
    """钩子结果聚合器

    合并多个钩子的执行结果：
    - deny 优先：任何 deny 都导致最终 deny
    - ask 汇总：收集所有 ask 的原因
    - allow 统计：记录允许的钩子数量
    """

    @staticmethod
    def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
        """聚合多个钩子结果

        Args:
            results: 钩子执行结果列表

        Returns:
            聚合后的最终决策
        """
        if not results:
            return {"decision": PermissionDecision.Allow.value, "reasons": []}

        # deny 优先
        deny_reasons = [
            r.get("reason", "Security violation")
            for r in results
            if r.get("decision") == PermissionDecision.Deny.value
        ]
        if deny_reasons:
            return {
                "decision": PermissionDecision.Deny.value,
                "reasons": deny_reasons,
                "message": f"Denied by hooks: {deny_reasons[0]}",
            }

        # ask 汇总
        ask_reasons = [
            r.get("reason", "Needs confirmation")
            for r in results
            if r.get("decision") == PermissionDecision.Ask.value
        ]
        if ask_reasons:
            return {
                "decision": PermissionDecision.Ask.value,
                "reasons": ask_reasons,
                "message": f"Confirmation required: {', '.join(ask_reasons)}",
            }

        # 全部 allow
        return {
            "decision": PermissionDecision.Allow.value,
            "reasons": [],
            "allowed_count": len(results),
        }


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
        """注册响应处理器

        Args:
            request_type: 请求类型
            handler: 处理函数
        """
        if request_type not in self._handlers:
            self._handlers[request_type] = []
        self._handlers[request_type].append(handler)
        logger.debug(f"Handler registered: type={request_type}")

    async def request(
        self,
        request_type: str,
        payload: dict[str, Any],
        timeout_ms: int = 60000,
        abort_signal: Optional[Any] = None,
    ) -> dict[str, Any]:
        """发送请求并等待响应

        Args:
            request_type: 请求类型
            payload: 请求数据
            timeout_ms: 超时时间（毫秒）
            abort_signal: AbortSignal 实例（可选）

        Returns:
            响应数据

        Raises:
            TimeoutError: 请求超时
            asyncio.CancelledError: 被 AbortSignal 取消
        """
        correlation_id = str(uuid.uuid4())
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()

        # 注册等待请求
        pending = PendingRequest(
            correlation_id=correlation_id,
            request_type=request_type,
            future=future,
            timeout_ms=timeout_ms,
        )

        async with self._lock:
            self._pending_requests[correlation_id] = pending

        # 设置 AbortSignal 监听器
        cancel_callback = None
        if abort_signal is not None:
            cancel_callback = lambda: self._cancel_request(correlation_id)
            # 尝试添加监听器（如果 signal 支持）
            if hasattr(abort_signal, "add_listener"):
                abort_signal.add_listener(cancel_callback)
            elif hasattr(abort_signal, "add_done_callback"):
                abort_signal.add_done_callback(cancel_callback)

        # 发送请求
        full_request = {
            **payload,
            "correlation_id": correlation_id,
            "request_type": request_type,
        }
        await self._dispatch_request(request_type, full_request)

        try:
            # 等待响应
            result = await asyncio.wait_for(
                future,
                timeout=timeout_ms / 1000,
            )
            return result
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise TimeoutError(f"Request timeout: {request_type}")
        except asyncio.CancelledError:
            async with self._lock:
                self._pending_requests.pop(correlation_id, None)
            raise
        finally:
            # 清理监听器
            if cancel_callback and abort_signal is not None:
                if hasattr(abort_signal, "remove_listener"):
                    abort_signal.remove_listener(cancel_callback)

    async def respond(
        self,
        correlation_id: str,
        response: dict[str, Any],
    ) -> bool:
        """发送响应

        Args:
            correlation_id: 关联 ID
            response: 响应数据

        Returns:
            True 如果成功响应，False 如果请求已超时/取消
        """
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

    async def _dispatch_request(
        self,
        request_type: str,
        request: dict[str, Any],
    ) -> None:
        """分发请求到处理器"""
        handlers = self._handlers.get(request_type, [])

        if not handlers:
            # 无处理器时自动返回默认响应
            await self.respond(
                request["correlation_id"],
                {"decision": PermissionDecision.Allow.value, "handled": False},
            )
            return

        # 调用所有处理器
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

        # 聚合结果
        aggregated = HookAggregator.aggregate_results(results)
        await self.respond(request["correlation_id"], aggregated)

    def _cancel_request(self, correlation_id: str) -> None:
        """取消等待中的请求"""
        async def _cancel():
            async with self._lock:
                pending = self._pending_requests.pop(correlation_id, None)
                if pending and not pending.future.done():
                    pending.future.cancel()

        # 在事件循环中执行
        try:
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.create_task(_cancel())
            )
        except RuntimeError:
            # 无运行中的事件循环
            pass

    def get_pending_count(self) -> int:
        """获取等待中的请求数量"""
        return len(self._pending_requests)

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()


# 全局单例
_global_message_bus: Optional[LifecycleMessageBus] = None


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
    "PermissionDecision",
    "PendingRequest",
    "HookAggregator",
    "LifecycleMessageBus",
    "get_message_bus",
    "reset_message_bus",
]