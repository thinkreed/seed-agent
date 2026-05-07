"""
Harness (控制器) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- Harness 是控制器（双手），驱动运行循环
- 从 Session 拉取上下文 → 调用 LLM API → 路由工具调用
- 本身无状态，可随时创建、销毁、替换
- 不持有对话历史，只通过 SessionEventStream 访问

公共接口：
- Harness: 主控制器类
- CycleResult: 单轮循环结果类型
- ToolExecutionMetrics: 工具执行指标类型
- MaxIterationsExceededError: 最大迭代次数错误
- LoopDetectedError: 循环检测错误
- HarnessManager: 多实例管理器（从 harness._manager 导入）

内部模块位于 src/harness/ 目录：
- _metrics: 指标和 OpenTelemetry Span
- _loop_detection: 循环检测服务
- _write_conflict: 写冲突检测
- _lifecycle_hooks: 钩子触发和上下文构建
- _single_tool: 单工具执行
- _tool_router: 工具路由
- _context_builder: 上下文构建
- _cycle: 核心循环逻辑
- _streaming: 流式处理
- _resume: 恢复执行
- _manager: HarnessManager 类
"""

import logging
from collections import deque
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.context_engineering import ContextEngineering
from src.harness._context_builder import (
    build_context_from_session,
    build_context_from_session_async,
)
from src.harness._cycle import run_conversation_impl, run_cycle_impl
from src.harness._lifecycle_hooks import build_session_end_ctx, trigger_hook
from src.harness._loop_detection import (
    LoopDetectionService,
    LoopType,
)
from src.harness._manager import MAX_ITERATIONS, HarnessManager

# 从子模块导入
from src.harness._metrics import ToolExecutionMetrics
from src.harness._resume import resume_with_user_response
from src.harness._streaming import stream_conversation, stream_resume_with_user_response
from src.harness._tool_router import (
    execute_tools_parallel_with_hooks,
    route_tool_calls_with_hooks,
)
from src.lifecycle_hooks import HookPoint, HookTriggerReport, LifecycleHookRegistry
from src.llm_client import LLMClient
from src.request_queue import RequestPriority
from src.sandbox import Sandbox
from src.session_event_stream import SessionEventStream

if TYPE_CHECKING:
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)


class MaxIterationsExceededError(Exception):
    """超过最大迭代次数"""

    def __init__(self, iterations: int) -> None:
        super().__init__(f"Harness exceeded maximum iterations ({iterations})")
        self.iterations = iterations


class LoopDetectedError(Exception):
    """检测到循环调用"""

    def __init__(self, loop_type: LoopType, tool_name: str | None = None, count: int = 0) -> None:
        message = f"Loop detected: {loop_type.name}"
        if tool_name:
            message += f" (tool: {tool_name})"
        if count:
            message += f" (count: {count})"
        super().__init__(message)
        self.loop_type = loop_type
        self.tool_name = tool_name
        self.count = count


class CycleResult(dict):
    """单轮循环结果（TypedDict 兼容）"""
    pass


class Harness:
    """Harness 控制器 - 无状态驱动 + 生命周期钩子 + Ask User + 取消支持

    三件套解耦架构中的"控制器"层：
    - 无状态：不持有历史，只通过 Session 访问
    - 驱动循环：run_cycle → run_conversation
    - 路由工具：将 tool_calls 转发到 Sandbox
    - 记录事件：将响应和结果写入 Session
    - 钩子触发：在关键节点自动触发预设动作
    """

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

    # === 内部辅助 ===

    async def _trigger_hook(self, hook_point: HookPoint, context: dict[str, Any]) -> HookTriggerReport | None:
        report = await trigger_hook(self._hook_registry, hook_point, context)
        if report:
            self._hook_reports.append(report)
        return report

    def _build_session_end_ctx(self, reason: str, error: str | None = None, final_response: str | None = None) -> dict[str, Any]:
        return build_session_end_ctx(self.session, self, reason, error, final_response)

    # === 核心循环 ===

    async def run_cycle(self, priority: int = RequestPriority.NORMAL, signal: AbortSignal | None = None) -> CycleResult:
        """执行一轮对话循环"""
        result = await run_cycle_impl(
            self.llm_client, self.session, self.sandbox, self._hook_registry, self._metrics,
            self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self.autonomous_mode, self._ask_user_skip_response, self, priority, signal
        )
        return CycleResult(result)

    async def run_conversation(self, initial_prompt: str, priority: int = RequestPriority.CRITICAL, signal: AbortSignal | None = None) -> dict[str, Any]:
        """执行完整对话"""
        try:
            return await run_conversation_impl(
                initial_prompt, self.llm_client, self.session, self.sandbox, self._hook_registry,
                self._metrics, self.max_iterations, self._context_window, self._context_engineering,
                self._current_task, self.system_prompt, self._enable_pruning,
                self.autonomous_mode, self._ask_user_skip_response, self, priority, signal
            )
        except RuntimeError as e:
            if str(e).startswith("MaxIterationsExceeded:"):
                iterations = int(str(e).split(":")[1])
                raise MaxIterationsExceededError(iterations)
            raise

    async def resume_with_user_response(self, response: "AskUserResult", priority: int = RequestPriority.CRITICAL, signal: AbortSignal | None = None) -> dict[str, Any]:
        """恢复执行（用户响应后）"""
        return await resume_with_user_response(
            response, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self._pending_tool_call_id, priority, signal
        )

    # === 流式处理 ===

    async def stream_conversation(self, initial_prompt: str, priority: int = RequestPriority.CRITICAL, signal: AbortSignal | None = None) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行对话"""
        async for chunk in stream_conversation(
            initial_prompt, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self.autonomous_mode, self._ask_user_skip_response, priority, signal
        ):
            yield chunk

    async def stream_resume_with_user_response(self, response: "AskUserResult", priority: int = RequestPriority.CRITICAL, signal: AbortSignal | None = None) -> AsyncGenerator[dict[str, Any], None]:
        """流式恢复执行"""
        async for chunk in stream_resume_with_user_response(
            response, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self._pending_tool_call_id, priority, signal
        ):
            yield chunk

    # === 上下文构建 ===

    def _build_context_from_session(self) -> list[dict[str, Any]]:
        return build_context_from_session(
            self.session, self._context_engineering, self._context_window,
            self._current_task, self.system_prompt, self._enable_pruning
        )

    async def _build_context_from_session_async(self) -> list[dict[str, Any]]:
        return await build_context_from_session_async(
            self.session, self._context_engineering, self._context_window,
            self._current_task, self.system_prompt, self._enable_pruning
        )

    def set_current_task(self, task: str) -> None:
        self._current_task = task

    def set_autonomous_mode(self, enabled: bool, skip_response: str | None = None) -> None:
        self.autonomous_mode = enabled
        if skip_response is not None:
            self._ask_user_skip_response = skip_response

    # === 状态恢复 ===

    def replay_to_event(self, target_event_id: int) -> dict[str, Any]:
        return self.session.replay_to_state(target_event_id)

    def get_current_state(self) -> dict[str, Any]:
        return self.session.get_current_state()

    # === 辅助方法 ===

    def get_session_id(self) -> str:
        return self.session.session_id

    def get_event_count(self) -> int:
        return self.session.get_event_count()

    def get_metrics(self) -> list[ToolExecutionMetrics]:
        return list(self._metrics)

    def clear_metrics(self) -> None:
        self._metrics.clear()

    def get_status(self) -> dict[str, Any]:
        return {
            "session_id": self.session.session_id,
            "event_count": self.session.get_event_count(),
            "max_iterations": self.max_iterations,
            "llm_model": self.llm_client.model_id,
            "tools_registered": len(self.sandbox.get_tool_schemas()),
            "metrics_count": len(self._metrics),
            "hooks_enabled": self._hook_registry is not None,
        }

    def get_hook_registry(self) -> LifecycleHookRegistry | None:
        return self._hook_registry

    def get_hook_reports(self) -> list[HookTriggerReport]:
        return list(self._hook_reports)

    def clear_hook_reports(self) -> None:
        self._hook_reports.clear()

    # === 向后兼容 ===

    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        return await route_tool_calls_with_hooks(
            tool_calls, self.session, self, self.sandbox, self._hook_registry, self._metrics
        )

    async def _execute_tools_parallel(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        return await execute_tools_parallel_with_hooks(
            tool_calls, self.session, self, self.sandbox, self._hook_registry, self._metrics
        )


__all__ = ["MAX_ITERATIONS", "CycleResult", "Harness", "HarnessManager", "LoopDetectedError", "LoopDetectionService", "LoopType", "MaxIterationsExceededError", "ToolExecutionMetrics"]