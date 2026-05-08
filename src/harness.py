"""
Harness (控制器) 模块

三件套解耦架构的控制器层：驱动运行循环、路由工具调用。
无状态设计，可随时创建、销毁、替换。

公共接口：Harness, CycleResult, MaxIterationsExceededError, LoopDetectedError
内部模块：src/harness/ 目录下的 _errors, _state, _execution 等
"""

import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.context_engineering import ContextEngineering
from src.harness._errors import CycleResult, LoopDetectedError, MaxIterationsExceededError
from src.harness._execution import HarnessExecutionMixin
from src.harness._lifecycle_hooks import build_session_end_ctx, trigger_hook
from src.harness._loop_detection import LoopDetectionService, LoopType
from src.harness._manager import MAX_ITERATIONS, HarnessManager
from src.harness._metrics import ToolExecutionMetrics
from src.harness._state import HarnessStateMixin
from src.harness._tool_router import execute_tools_parallel_with_hooks, route_tool_calls_with_hooks
from src.lifecycle_hooks import HookPoint, HookTriggerReport, LifecycleHookRegistry
from src.llm_client import LLMClient
from src.request_queue import RequestPriority
from src.sandbox import Sandbox
from src.session_event_stream import SessionEventStream

if TYPE_CHECKING:
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)


class Harness(HarnessStateMixin, HarnessExecutionMixin):
    """Harness 控制器 - 无状态驱动 + 生命周期钩子 + Ask User + 取消支持"""

    def __init__(
        self,
        llm_client: LLMClient,
        session: SessionEventStream,
        sandbox: Sandbox,
        max_iterations: int = MAX_ITERATIONS,
        system_prompt: str | None = None,
        context_engineering: ContextEngineering | None = None,
        context_window: int = 100000,
        enable_pruning: bool = True,
        hook_registry: LifecycleHookRegistry | None = None,
        autonomous_mode: bool = False,
        ask_user_skip_response: str | None = None,
    ):
        self.llm_client = llm_client
        self.session = session
        self.sandbox = sandbox
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self._context_engineering = context_engineering
        self._context_window = context_window
        self._enable_pruning = enable_pruning
        self._hook_registry = hook_registry
        self.autonomous_mode = autonomous_mode
        if ask_user_skip_response is None:
            from src.shared_config import get_autonomous_config
            self._ask_user_skip_response = get_autonomous_config().ask_user_skip_response
        else:
            self._ask_user_skip_response = ask_user_skip_response
        self._current_task: str | None = None
        self._metrics: deque[ToolExecutionMetrics] = deque(maxlen=1000)
        self._hook_reports: deque[HookTriggerReport] = deque(maxlen=500)
        self._loop_detector: LoopDetectionService = LoopDetectionService()
        self._waiting_for_user: bool = False
        self._pending_tool_call_id: str | None = None
        logger.info(f"Harness initialized: session={session.session_id}")

    async def _trigger_hook(self, hook_point: HookPoint, context: dict[str, Any]) -> HookTriggerReport | None:
        """触发钩子"""
        report = await trigger_hook(self._hook_registry, hook_point, context)
        if report:
            self._hook_reports.append(report)
        return report

    def _build_session_end_ctx(self, reason: str, error: str | None = None, final_response: str | None = None) -> dict[str, Any]:
        """构建会话结束上下文"""
        return build_session_end_ctx(self.session, self, reason, error, final_response)

    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """路由工具调用（向后兼容）"""
        return await route_tool_calls_with_hooks(
            tool_calls, self.session, self, self.sandbox, self._hook_registry, self._metrics
        )

    async def _execute_tools_parallel(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """并行执行工具（向后兼容）"""
        return await execute_tools_parallel_with_hooks(
            tool_calls, self.session, self, self.sandbox, self._hook_registry, self._metrics
        )


__all__ = ["MAX_ITERATIONS", "CycleResult", "Harness", "HarnessManager", "LoopDetectedError", "LoopDetectionService", "LoopType", "MaxIterationsExceededError", "ToolExecutionMetrics"]