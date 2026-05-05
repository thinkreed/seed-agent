"""
Harness 流式迭代循环

提取流式对话的迭代循环逻辑。

内容:
- run_iteration_loop - 运行迭代循环（通用模式）
"""

import logging
from collections import deque
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortSignal
from src.request_queue import RequestPriority
from src.session_event_stream import EventType

from ._context_builder import build_context_from_session
from ._lifecycle_hooks import build_session_end_ctx, trigger_hook
from ._streaming_executor import execute_iteration, extract_iteration_result, is_iteration_result
from ._streaming_iteration import IterationOutcome, handle_tool_execution
from ._streaming_types import StreamChunkType
from ._streaming_utils import check_cancelled, get_cancel_reason

if TYPE_CHECKING:
    from src.lifecycle_hooks import LifecycleHookRegistry
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

    from ._metrics import ToolExecutionMetrics

logger = logging.getLogger(__name__)


async def run_iteration_loop(
    llm_client: "LLMClient",
    session: "SessionEventStream",
    sandbox: "Sandbox",
    harness_ref: Any,
    hook_registry: "LifecycleHookRegistry | None",
    metrics_deque: deque["ToolExecutionMetrics"],
    max_iterations: int,
    context_window: int,
    context_engineering: Any,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    autonomous_mode: bool = False,
    ask_user_skip_response: str = "",
    priority: int = RequestPriority.CRITICAL,
    signal: AbortSignal | None = None,
    start_iteration: int = 0,
) -> AsyncGenerator[dict[str, Any], None]:
    """运行迭代循环（通用模式）"""
    iteration = start_iteration

    try:
        while iteration < max_iterations:
            if check_cancelled(signal):
                session.emit_event(EventType.EXECUTION_CANCEL,
                    {"reason": get_cancel_reason(signal), "iteration": iteration})
                yield {"type": StreamChunkType.CANCELLED, "reason": get_cancel_reason(signal)}
                return

            iteration += 1
            logger.debug(f"iteration {iteration}/{max_iterations}")

            context = build_context_from_session(
                session, context_engineering, context_window, current_task, system_prompt, enable_pruning)
            tools = sandbox.get_tool_schemas()

            # 执行迭代
            iter_result = await _collect_iteration_result(llm_client, context, tools, priority)
            if iter_result is None:
                continue

            # 记录响应
            full_content, tool_calls = iter_result["full_content"], iter_result["tool_calls"]
            llm_data: dict[str, Any] = {}
            if full_content:
                llm_data["content"] = full_content
            if tool_calls:
                llm_data["tool_calls"] = tool_calls
            session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 处理工具执行
            outcome, data = await handle_tool_execution(
                iter_result, session, harness_ref, sandbox, hook_registry, metrics_deque,
                autonomous_mode, ask_user_skip_response)

            for chunk in _yield_outcome_chunks(outcome, data):
                yield chunk

            # COMPLETED 表示对话结束，退出循环
            if outcome == IterationOutcome.COMPLETED:
                return

        session.record_session_end("max_iterations_exceeded")
        raise Exception(f"Max iterations exceeded ({max_iterations})")

    except Exception as e:
        await trigger_hook(hook_registry, "SESSION_END",
            build_session_end_ctx(session, harness_ref, "error", error=str(e))
        )  # type: ignore[arg-type]
        session.record_session_end("error")
        yield {"type": StreamChunkType.ERROR, "content": str(e)}


async def _collect_iteration_result(
    llm_client: "LLMClient",
    context: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    priority: int,
) -> dict[str, Any] | None:
    """执行迭代并收集结果"""
    iteration_result = None
    async for chunk in execute_iteration(llm_client, context, tools, priority):
        if is_iteration_result(chunk):
            iteration_result = extract_iteration_result(chunk)
    return iteration_result


def _yield_outcome_chunks(outcome: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """根据 outcome 生成响应 chunks"""
    if outcome == IterationOutcome.COMPLETED:
        return [{"type": StreamChunkType.FINAL, "content": data["content"]}]
    elif outcome == IterationOutcome.AWAITING_INPUT:
        return [{"type": StreamChunkType.AWAITING_USER_INPUT, "request": data["request"]}]
    elif outcome == IterationOutcome.AUTONOMOUS_SKIP:
        return []
    elif outcome == IterationOutcome.CONTINUE:
        return [{"type": StreamChunkType.TOOL_END, "result": r["content"]} for r in data["tool_results"]]
    return []