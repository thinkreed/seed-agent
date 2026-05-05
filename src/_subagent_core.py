"""Subagent 核心模块"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from src._subagent_config import DEFAULT_TIMEOUTS
from src._subagent_tools import execute_tool_calls, get_system_prompt, setup_tools
from src._subagent_types import SubagentState, SubagentType, _get_subagent_type_key
from src.client import LLMGateway
from src.observability import SPAN_SUBAGENT_EXECUTE, StatusCode, get_tracer, is_observability_enabled, set_subagent_span_attributes
from src.tools import ToolRegistry

_OBSERVABILITY_ENABLED = is_observability_enabled()
logger = logging.getLogger(__name__)


class SubagentInstance:
    """独立上下文的 Subagent 执行实例"""

    MAX_SUBAGENT_ITERATIONS = 100

    def __init__(self, gateway: LLMGateway, subagent_type: SubagentType, model_id: str | None = None,
                 max_iterations: int = MAX_SUBAGENT_ITERATIONS, timeout: int | None = None,
                 custom_system_prompt: str | None = None, custom_tools: set[str] | None = None):
        self.gateway = gateway
        self.subagent_type = subagent_type
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.timeout = timeout or DEFAULT_TIMEOUTS.get(_get_subagent_type_key(subagent_type), 300)
        self.history: list[dict] = []
        self.tools = ToolRegistry()
        self._allowed_tools = setup_tools(self.tools, subagent_type, custom_tools)
        self.system_prompt = get_system_prompt(subagent_type, custom_system_prompt)
        self.state: SubagentState | None = None

    def _get_primary_model(self) -> str:
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def _build_messages(self) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        return messages

    async def run(self, prompt: str, task_id: str | None = None) -> SubagentState:
        """执行 Subagent 任务"""
        task_id = task_id or str(uuid.uuid4())[:8]
        self.state = SubagentState(id=task_id, subagent_type=self.subagent_type, status="pending", prompt=prompt)
        self.state.started_at = datetime.now(UTC)
        self.state.status = "running"
        self.history.append({"role": "user", "content": prompt})

        tracer = get_tracer()
        span = None
        start_time = time.time()

        if tracer and _OBSERVABILITY_ENABLED:
            span = tracer.start_span(SPAN_SUBAGENT_EXECUTE)
            set_subagent_span_attributes(span, subagent_type=self.subagent_type.value, task_id=task_id, status="running")

        try:
            result = await asyncio.wait_for(self._run_loop(), timeout=self.timeout)
            self.state.status = "completed"
            self.state.result = result
            if span:
                span.set_attribute("seed.subagent.status", "completed")
                span.set_attribute("seed.subagent.duration_ms", (time.time() - start_time) * 1000)
                span.set_status(StatusCode.OK)

        except TimeoutError:
            logger.warning(f"Subagent {task_id} timed out after {self.timeout}s")
            self.state.status = "timeout"
            self.state.error = f"Execution timed out after {self.timeout} seconds"
            if span:
                span.set_attribute("seed.subagent.status", "timeout")
                span.set_status(StatusCode.ERROR)

        except Exception as e:
            logger.exception(f"Subagent {task_id} failed: {e}")
            self.state.status = "failed"
            self.state.error = str(e)
            if span:
                span.record_exception(e)
                span.set_status(StatusCode.ERROR, str(e)[:200])

        finally:
            self.state.completed_at = datetime.now(UTC)
            if span:
                span.end()

        return self.state

    async def _run_loop(self) -> str:
        """主执行循环"""
        if self.state is None:
            raise RuntimeError("SubagentState must be initialized before _run_loop")

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            self.state.iterations = iteration

            messages = self._build_messages()
            response = await self.gateway.chat_completion(self.model_id, messages, tools=self.tools.get_schemas())
            choices = response.get("choices", [])
            if not choices:
                logger.warning("Subagent: LLM returned empty choices")
                return ""

            message = choices[0].get("message", {})
            self.history.append(message)

            if message.get("tool_calls"):
                tool_results = await execute_tool_calls(self.tools, message["tool_calls"])
                self.history.extend(tool_results)
            else:
                return message.get("content", "")

        raise RuntimeError(f"Subagent exceeded maximum iterations ({self.max_iterations})")