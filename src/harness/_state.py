"""
Harness 状态管理方法

从 harness.py 拆分的状态访问/修改方法：
- get_*: 状态获取
- set_*: 状态设置
- clear_*: 状态清理
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.harness._metrics import ToolExecutionMetrics
from src.lifecycle_hooks import HookTriggerReport, LifecycleHookRegistry

if TYPE_CHECKING:
    from src.tools.ask_user_types import AskUserResult


class HarnessStateMixin:
    """Harness 状态管理混入类

    提供状态访问、修改和清理方法。
    这些方法不依赖其他混入类，可独立使用。
    """

    # 以下属性由 Harness 主类提供，类型注解仅供 mypy 参考
    session: Any
    llm_client: Any
    sandbox: Any
    max_iterations: int
    _hook_registry: LifecycleHookRegistry | None
    _metrics: Any
    _hook_reports: Any
    _current_task: str | None
    _context_window: int
    _context_engineering: Any
    _enable_pruning: bool
    _pending_tool_call_id: str | None
    system_prompt: str | None
    autonomous_mode: bool
    _ask_user_skip_response: str

    # === 任务设置 ===

    def set_current_task(self: Any, task: str) -> None:
        """设置当前任务"""
        self._current_task = task

    def set_autonomous_mode(self: Any, enabled: bool, skip_response: str | None = None) -> None:
        """设置自主模式"""
        self.autonomous_mode = enabled
        if skip_response is not None:
            self._ask_user_skip_response = skip_response

    # === 状态恢复 ===

    def replay_to_event(self: Any, target_event_id: int) -> dict[str, Any]:
        """重放到指定事件"""
        return self.session.replay_to_state(target_event_id)

    def get_current_state(self: Any) -> dict[str, Any]:
        """获取当前状态"""
        return self.session.get_current_state()

    # === 辅助方法 ===

    def get_session_id(self: Any) -> str:
        """获取会话 ID"""
        return self.session.session_id

    def get_event_count(self: Any) -> int:
        """获取事件计数"""
        return self.session.get_event_count()

    def get_metrics(self: Any) -> list[ToolExecutionMetrics]:
        """获取指标列表"""
        return list(self._metrics)

    def clear_metrics(self: Any) -> None:
        """清理指标"""
        self._metrics.clear()

    def get_status(self: Any) -> dict[str, Any]:
        """获取状态摘要"""
        return {
            "session_id": self.session.session_id,
            "event_count": self.session.get_event_count(),
            "max_iterations": self.max_iterations,
            "llm_model": self.llm_client.model_id,
            "tools_registered": len(self.sandbox.get_tool_schemas()),
            "metrics_count": len(self._metrics),
            "hooks_enabled": self._hook_registry is not None,
        }

    def get_hook_registry(self: Any) -> LifecycleHookRegistry | None:
        """获取钩子注册表"""
        return self._hook_registry

    def get_hook_reports(self: Any) -> list[HookTriggerReport]:
        """获取钩子报告"""
        return list(self._hook_reports)

    def clear_hook_reports(self: Any) -> None:
        """清理钩子报告"""
        self._hook_reports.clear()


__all__ = ["HarnessStateMixin"]