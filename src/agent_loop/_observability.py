"""
AgentLoop 可观测性层

职责:
- OpenTelemetry Span 管理
- 状态查询接口
- 钩子统计
"""

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)

if TYPE_CHECKING:
    from opentelemetry.trace import Span

    from src.lifecycle_hooks import LifecycleHookRegistry

logger = logging.getLogger(__name__)

_OBSERVABILITY_ENABLED = is_observability_enabled()


class ObservabilityManager:
    """可观测性管理器"""

    def __init__(self, session, hook_registry: "LifecycleHookRegistry | None", harness):
        self.session = session
        self._hook_registry = hook_registry
        self.harness = harness

    def start_tool_span(self, tool_name: str, tool_args: dict) -> "Span | None":
        """创建工具 Span"""
        tracer = get_tracer()
        if not (tracer and _OBSERVABILITY_ENABLED):
            return None

        span = tracer.start_span(f"{SPAN_TOOL_PREFIX}{tool_name}")
        set_tool_span_attributes(span, tool_name, file_path=tool_args.get("path", ""))
        return span

    def finish_tool_span(
        self,
        span: "Span | None",
        start_time: float,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """完成 Span"""
        if not span:
            return

        duration_ms = (time.time() - start_time) * 1000
        if success:
            span.set_attribute("seed.tool.duration_ms", duration_ms)
            span.set_status(StatusCode.OK)
        elif error:
            span.record_exception(error)
            span.set_attribute("seed.error.message", str(error)[:500])
            span.set_status(StatusCode.ERROR, str(error)[:200])
        span.end()

    # === 状态恢复 ===

    def replay_to_event(self, event_id: int) -> dict[str, Any]:
        """重放事件到指定状态"""
        return self.session.replay_to_state(event_id)

    def get_current_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return self.session.get_current_state()

    def get_event_count(self) -> int:
        """获取事件总数"""
        return self.session.get_event_count()

    # === 状态查询 ===

    def get_status(
        self,
        session_id: str,
        model_id: str,
        conversation_rounds: int,
        context_window: int,
        sandbox,
        enable_pruning: bool,
        compression_config,
        context_engineering,
    ) -> dict[str, Any]:
        """获取 AgentLoop 状态"""
        return {
            "session_id": session_id,
            "model_id": model_id,
            "event_count": self.session.get_event_count(),
            "conversation_rounds": conversation_rounds,
            "context_window": context_window,
            "isolation_level": sandbox.isolation_level.value,
            "harness_status": self.harness.get_status(),
            "context_engineering": {
                "enabled": context_engineering is not None,
                "pruning_enabled": enable_pruning,
                "compression_configured": compression_config is not None,
            },
            "hooks": {
                "registry": self._hook_registry is not None,
                "hooks_registered": self._hook_registry.get_hook_count()
                if self._hook_registry
                else 0,
                "hook_reports": len(self.harness.get_hook_reports()),
            },
        }

    def get_hook_registry(self) -> "LifecycleHookRegistry | None":
        """获取钩子注册中心"""
        return self._hook_registry

    def get_hook_stats(self) -> dict[str, Any]:
        """获取钩子执行统计"""
        if self._hook_registry:
            return self._hook_registry.get_all_stats()
        return {"global": {}, "hooks": {}}

    def register_custom_hook(
        self,
        hook_point: str,
        callback: Callable[..., Any],
        priority: int = 100,
        name: str | None = None,
    ) -> str | None:
        """注册自定义钩子"""
        if self._hook_registry:
            from src.lifecycle_hooks import HookPoint

            point: HookPoint | str
            try:
                point = HookPoint(hook_point)
            except ValueError:
                point = hook_point
            result = self._hook_registry.register(
                point, callback, priority=priority, name=name
            )
            return result if isinstance(result, str) else None
        return None