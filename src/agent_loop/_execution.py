"""
Agent 执行流程模块

提供核心执行方法：
- run: 执行对话
- stream_run: 流式执行对话
- _handle_user_wait: 处理用户等待

核心特性：
- 取消控制集成
- 摘要触发
- Skill outcome 记录
"""

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortController, AbortSignal
from src.harness import MaxIterationsExceededError
from src.request_queue import RequestPriority
from src.tools.ask_user_types import AskUserResult

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger(__name__)


class ExecutionMixin:
    """执行流程功能 Mixin

    提供 run, stream_run, _handle_user_wait 方法。
    需要与 AgentLoop 配合使用。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        harness: Any
        session: Any
        session_id: str
        system_prompt: str
        _summarizer: Any
        _skill_tracker: Any
        _abort_controller: AbortController
        _user_input_event: Any
        _pending_user_response: AskUserResult | None

    async def run(
        self: "AgentLoop",
        user_input: str,
        priority: int = RequestPriority.CRITICAL,
        wait_for_user: bool = True,
    ) -> str:
        """执行对话"""
        self._summarizer.increment_rounds()
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal

        try:
            result = await self.harness.run_conversation(user_input, priority, signal)

            if result["status"] == "waiting_for_user":
                if wait_for_user:
                    await self._user_input_event.wait()
                    user_response = self._pending_user_response
                    self._user_input_event.clear()
                    self._pending_user_response = None

                    final_result = await self.harness.resume_with_user_response(
                        user_response, priority, signal
                    )
                    if final_result["status"] == "completed":
                        await self._summarizer.maybe_summarize(
                            self.system_prompt, self.session_id
                        )
                        self._skill_tracker.evaluate_and_record_skill_outcomes(True)
                        return final_result["content"]
                    return f"[{final_result['status']}]"
                return "[AWAITING_USER_INPUT]"

            if result["status"] == "completed":
                await self._summarizer.maybe_summarize(self.system_prompt, self.session_id)
                self._skill_tracker.evaluate_and_record_skill_outcomes(True)
                return result["content"]

            return f"[{result['status']}]"

        except MaxIterationsExceededError:
            logger.exception("Max iterations exceeded")
            self.session.record_session_end("max_iterations_exceeded")
            raise
        finally:
            self._pending_user_response = None
            self._user_input_event.clear()

    async def stream_run(
        self: "AgentLoop",
        user_input: str,
        priority: int = RequestPriority.CRITICAL,
    ) -> AsyncGenerator[dict, None]:
        """流式执行对话"""
        self._summarizer.increment_rounds()
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal
        self.harness.set_current_task(user_input)

        try:
            async for chunk in self.harness.stream_conversation(user_input, priority, signal):
                if signal.aborted:
                    yield {"type": "cancelled", "reason": signal.reason}
                    return

                chunk_type = chunk.get("type")

                if chunk_type == "awaiting_user_input":
                    yield chunk
                    await self._handle_user_wait(priority, signal)
                    return

                elif chunk_type == "final":
                    await self._summarizer.maybe_summarize(self.system_prompt, self.session_id)
                    self._skill_tracker.evaluate_and_record_skill_outcomes(True)
                    yield chunk
                    return

                elif chunk_type in {"cancelled", "error"}:
                    yield chunk
                    return

                else:
                    yield chunk

        except MaxIterationsExceededError as e:
            yield {"type": "error", "content": str(e)}
        finally:
            self._pending_user_response = None
            self._user_input_event.clear()

    async def _handle_user_wait(
        self: "AgentLoop", priority: int, signal: AbortSignal
    ) -> None:
        """处理用户等待"""
        await self._user_input_event.wait()
        user_response = self._pending_user_response
        self._user_input_event.clear()
        self._pending_user_response = None

        # 流式恢复执行（忽略中间 chunks）
        async for _ in self.harness.stream_resume_with_user_response(
            user_response, priority, signal
        ):
            pass