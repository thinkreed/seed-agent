"""
Harness 执行方法混入类

从 harness.py 拆分的核心执行方法：
- run_cycle: 单轮循环
- run_conversation: 完整对话
- resume_with_user_response: 恢复执行
- stream_conversation: 流式对话
- stream_resume_with_user_response: 流式恢复
- _build_context_from_session: 上下文构建
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.harness._context_builder import build_context_from_session, build_context_from_session_async
from src.harness._cycle import run_conversation_impl, run_cycle_impl
from src.harness._errors import CycleResult, MaxIterationsExceededError
from src.harness._resume import resume_with_user_response
from src.harness._streaming import stream_conversation, stream_resume_with_user_response
from src.request_queue import RequestPriority

if TYPE_CHECKING:
    from src.tools.ask_user_types import AskUserResult


class HarnessExecutionMixin:
    """Harness 执行方法混入类

    提供核心循环、流式处理和上下文构建方法。
    """

    # 类型注解（属性由 Harness 主类提供）
    llm_client: Any
    session: Any
    sandbox: Any
    _hook_registry: Any
    _metrics: Any
    max_iterations: int
    _context_window: int
    _context_engineering: Any
    _current_task: str | None
    system_prompt: str | None
    _enable_pruning: bool
    autonomous_mode: bool
    _ask_user_skip_response: str
    _pending_tool_call_id: str | None

    async def run_cycle(
        self: Any, priority: int = RequestPriority.NORMAL, signal: AbortSignal | None = None
    ) -> CycleResult:
        """执行一轮对话循环"""
        result = await run_cycle_impl(
            self.llm_client, self.session, self.sandbox, self._hook_registry, self._metrics,
            self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self.autonomous_mode, self._ask_user_skip_response, self, priority, signal
        )
        return CycleResult(result)

    async def run_conversation(
        self: Any, initial_prompt: str, priority: int = RequestPriority.CRITICAL,
        signal: AbortSignal | None = None
    ) -> dict[str, Any]:
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

    async def resume_with_user_response(
        self: Any, response: "AskUserResult", priority: int = RequestPriority.CRITICAL,
        signal: AbortSignal | None = None
    ) -> dict[str, Any]:
        """恢复执行（用户响应后）"""
        return await resume_with_user_response(
            response, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self._pending_tool_call_id, priority, signal
        )

    async def stream_conversation(
        self: Any, initial_prompt: str, priority: int = RequestPriority.CRITICAL,
        signal: AbortSignal | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行对话"""
        async for chunk in stream_conversation(
            initial_prompt, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self.autonomous_mode, self._ask_user_skip_response, priority, signal
        ):
            yield chunk

    async def stream_resume_with_user_response(
        self: Any, response: "AskUserResult", priority: int = RequestPriority.CRITICAL,
        signal: AbortSignal | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式恢复执行"""
        async for chunk in stream_resume_with_user_response(
            response, self.llm_client, self.session, self.sandbox, self._hook_registry,
            self._metrics, self.max_iterations, self._context_window, self._context_engineering,
            self._current_task, self.system_prompt, self._enable_pruning,
            self._pending_tool_call_id, priority, signal
        ):
            yield chunk

    def _build_context_from_session(self: Any) -> list[dict[str, Any]]:
        """构建上下文"""
        return build_context_from_session(
            self.session, self._context_engineering, self._context_window,
            self._current_task, self.system_prompt, self._enable_pruning
        )

    async def _build_context_from_session_async(self: Any) -> list[dict[str, Any]]:
        """异步构建上下文"""
        return await build_context_from_session_async(
            self.session, self._context_engineering, self._context_window,
            self._current_task, self.system_prompt, self._enable_pruning
        )


__all__ = ["HarnessExecutionMixin"]