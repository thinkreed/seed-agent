"""
Subagent 核心模块

包含 SubagentInstance 执行逻辑
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from src._subagent_config import (
    DEFAULT_TIMEOUTS,
    MAX_SUBAGENT_ITERATIONS,
    PERMISSION_SETS,
    SUBAGENT_SYSTEM_PROMPTS,
    SUBAGENT_TYPE_PERMISSIONS,
)
from src._subagent_types import (
    SubagentState,
    SubagentType,
    _get_subagent_type_key,
)
from src.client import LLMGateway
from src.observability import (
    SPAN_SUBAGENT_EXECUTE,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_subagent_span_attributes,
)
from src.tools import ToolRegistry
from src.tools.utils import parse_tool_arguments

_OBSERVABILITY_ENABLED = is_observability_enabled()

logger = logging.getLogger(__name__)


class SubagentInstance:
    """
    独立上下文的 Subagent 执行实例

    每个实例有独立的:
    - 对话历史 (history)
    - 工具集 (filtered tools)
    - 执行状态
    """

    MAX_SUBAGENT_ITERATIONS = 100  # Subagent 默认迭代上限较低

    def __init__(
        self,
        gateway: LLMGateway,
        subagent_type: SubagentType,
        model_id: str | None = None,
        max_iterations: int = MAX_SUBAGENT_ITERATIONS,
        timeout: int | None = None,
        custom_system_prompt: str | None = None,
        custom_tools: set[str] | None = None,
    ):
        """
        初始化 Subagent 实例

        Args:
            gateway: LLM 网关实例（复用父 agent 的）
            subagent_type: Subagent 类型
            model_id: 模型 ID（默认使用主模型）
            max_iterations: 最大迭代次数
            timeout: 超时时间（秒），默认根据任务类型动态设置
            custom_system_prompt: 自定义 system prompt
            custom_tools: 自定义工具集（覆盖默认权限集）
        """
        self.gateway = gateway
        self.subagent_type = subagent_type
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.timeout = timeout or DEFAULT_TIMEOUTS.get(
            _get_subagent_type_key(subagent_type), 300
        )

        # 独立的对话历史
        self.history: list[dict] = []

        # 工具注册
        self.tools = ToolRegistry()
        self._setup_tools(custom_tools)

        # System prompt
        base_prompt = SUBAGENT_SYSTEM_PROMPTS[_get_subagent_type_key(subagent_type)]
        self.system_prompt = custom_system_prompt or base_prompt

        # 状态
        self.state: SubagentState | None = None

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model

        return get_primary_model(self.gateway)

    def _setup_tools(self, custom_tools: set[str] | None = None):
        """设置工具集"""
        # 确定权限集
        type_key = _get_subagent_type_key(self.subagent_type)
        if custom_tools:
            allowed_tools = custom_tools
        else:
            permission_set_name = SUBAGENT_TYPE_PERMISSIONS[type_key]
            allowed_tools = PERMISSION_SETS[permission_set_name]

        self._allowed_tools = allowed_tools

        # 注册所有工具（后续会过滤）
        from src.tools.builtin_tools import register_builtin_tools
        from src.tools.memory_tools import register_memory_tools

        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)

        # 过滤工具
        self._filter_tools(allowed_tools)

    def _filter_tools(self, allowed: set[str]):
        """只保留允许的工具（一次性重建，避免逐个删除的低效操作）"""
        # 一次性重建字典，只保留允许的工具
        self.tools._tools = {
            name: tool for name, tool in self.tools._tools.items() if name in allowed
        }
        self.tools._tool_schemas = {
            name: schema
            for name, schema in self.tools._tool_schemas.items()
            if name in allowed
        }

    def _build_messages(self) -> list[dict]:
        """构建消息列表"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        return messages

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """执行工具调用"""
        results = []
        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = parse_tool_arguments(tool_call["function"]["arguments"])

            try:
                result = await self.tools.execute(tool_name, **tool_args)
                results.append(
                    {"role": "tool", "tool_call_id": tool_id, "content": str(result)}
                )
            except Exception as e:
                error_type = type(e).__name__
                full_error_msg = str(e)  # 保留完整错误信息
                truncated_msg = full_error_msg[:200]  # 截断用于返回给 LLM
                # 记录完整错误到日志（便于调试）
                logger.exception(
                    f"Tool {tool_name} failed: {error_type}: {full_error_msg}"
                )
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": f"Error in {tool_name}: {error_type} - {truncated_msg}",
                    }
                )

        return results

    async def run(self, prompt: str, task_id: str | None = None) -> SubagentState:
        """
        执行 Subagent 任务

        Args:
            prompt: 任务提示
            task_id: 任务 ID（可选，用于状态跟踪）

        Returns:
            SubagentState: 执行状态

        OpenTelemetry 嵌入点:
        - Span: seed.subagent.execute
        - Attributes: type, task_id, status
        """
        task_id = task_id or str(uuid.uuid4())[:8]
        self.state = SubagentState(
            id=task_id,
            subagent_type=self.subagent_type,
            status="pending",
            prompt=prompt,
        )
        self.state.started_at = datetime.now(UTC)
        self.state.status = "running"

        self.history.append({"role": "user", "content": prompt})

        # OpenTelemetry Span 创建
        tracer = get_tracer()
        span = None
        start_time = time.time()

        if tracer and _OBSERVABILITY_ENABLED:
            span = tracer.start_span(SPAN_SUBAGENT_EXECUTE)
            set_subagent_span_attributes(
                span,
                subagent_type=self.subagent_type.value,
                task_id=task_id,
                status="running",
            )

        try:
            # 超时执行
            result = await asyncio.wait_for(self._run_loop(), timeout=self.timeout)
            self.state.status = "completed"
            self.state.result = result

            # 记录成功
            if span:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("seed.subagent.status", "completed")
                span.set_attribute("seed.subagent.duration_ms", duration_ms)
                span.set_status(StatusCode.OK)

        except TimeoutError:
            logger.warning(f"Subagent {task_id} timed out after {self.timeout}s")
            self.state.status = "timeout"
            self.state.error = f"Execution timed out after {self.timeout} seconds"

            # 记录超时
            if span:
                span.set_attribute("seed.subagent.status", "timeout")
                span.set_attribute("seed.error.message", self.state.error)
                span.set_status(StatusCode.ERROR)

        except Exception as e:
            logger.exception(f"Subagent {task_id} failed: {e}")
            self.state.status = "failed"
            self.state.error = str(e)

            # 记录失败
            if span:
                span.record_exception(e)
                span.set_attribute("seed.subagent.status", "failed")
                span.set_attribute("seed.error.message", str(e)[:500])
                span.set_status(StatusCode.ERROR, str(e)[:200])

        finally:
            self.state.completed_at = datetime.now(UTC)
            if span:
                span.end()

        return self.state

    async def _run_loop(self) -> str:
        """主执行循环"""
        # 确保 state 已初始化（由 run() 方法设置）
        if self.state is None:
            raise RuntimeError(
                "SubagentState must be initialized before _run_loop. Call run() first."
            )

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            self.state.iterations = iteration

            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id, messages, tools=self.tools.get_schemas()
            )

            choices = response.get("choices", [])
            if not choices:
                logger.warning("Subagent: LLM returned empty choices")
                return ""
            choice = choices[0]
            message = choice.get("message", {})
            self.history.append(message)

            if message.get("tool_calls"):
                tool_results = await self._execute_tool_calls(message["tool_calls"])
                self.history.extend(tool_results)
            else:
                # 无工具调用 = 完成
                return message.get("content", "")

        raise RuntimeError(
            f"Subagent exceeded maximum iterations ({self.max_iterations})"
        )