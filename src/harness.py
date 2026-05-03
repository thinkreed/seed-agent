"""
Harness (控制器) 模块

基于 Harness Engineering "三件套解耦架构" 设计：
- Harness 是控制器（双手），驱动运行循环
- 从 Session 拉取上下文 → 调用 LLM API → 路由工具调用
- 本身无状态，可随时创建、销毁、替换
- 不持有对话历史，只通过 SessionEventStream 访问

上下文工程优化：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

核心职责：
1. 执行对话循环 (run_cycle)
2. 从 Session 构建优化上下文（上下文工程）
3. 调用 LLMClient 推理
4. 路由工具调用到 Sandbox
5. 记录事件到 Session

性能优化：
- 大脑(LLMClient)从容器(Sandbox)分离
- 首Token延迟降低 60-90%
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, TYPE_CHECKING, TypedDict

from src.llm_client import LLMClient
from src.context_engineering import ContextEngineering

if TYPE_CHECKING:
    from src.client import LLMGateway
    from src.context_engineering import CompressionConfig, PruningConfig
from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)
from src.request_queue import RequestPriority
from src.sandbox import Sandbox
from src.session_event_stream import EventType, SessionEventStream

logger = logging.getLogger(__name__)

# 最大迭代次数（安全上限）
MAX_ITERATIONS = 30

# OpenTelemetry 状态
_OBSERVABILITY_ENABLED = is_observability_enabled()

try:
    from opentelemetry.trace import Span
    _SPAN_TYPE_AVAILABLE = True
except ImportError:
    Span = None  # type: ignore[misc,assignment]
    _SPAN_TYPE_AVAILABLE = False


class MaxIterationsExceeded(Exception):
    """超过最大迭代次数"""
    def __init__(self, iterations: int) -> None:
        super().__init__(f"Harness exceeded maximum iterations ({iterations})")
        self.iterations = iterations


class CycleResult(TypedDict):
    """单轮循环结果"""
    response: dict[str, Any]
    tool_results: list[dict[str, Any]] | None
    continue_loop: bool


class ToolExecutionMetrics(TypedDict):
    """工具执行指标"""
    tool_name: str
    duration_ms: float
    success: bool
    error: str | None


class Harness:
    """Harness 控制器 - 无状态驱动

    三件套解耦架构中的"控制器"层：
    - 无状态：不持有历史，只通过 Session 访问
    - 驱动循环：run_cycle → run_conversation
    - 路由工具：将 tool_calls 转发到 Sandbox
    - 记录事件：将响应和结果写入 Session

    上下文工程优化：
    - 渐进式压缩：根据容量使用率动态压缩
    - 智能裁剪：根据任务相关性过滤历史
    - 原始数据不丢失：Session 保留完整历史

    关键特性：
    - 可替换：随时创建/销毁不影响 Session
    - 无状态：所有状态存储在 Session 中
    - 可观测：完整的事件流追踪 + OpenTelemetry
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
        enable_pruning: bool = True
    ):
        """初始化 Harness

        Args:
            llm_client: LLMClient (大脑)
            session: SessionEventStream (状态存储)
            sandbox: Sandbox (执行环境)
            max_iterations: 最大迭代次数
            system_prompt: 系统提示
            context_engineering: 上下文工程实例（可选）
            context_window: 上下文窗口大小
            enable_pruning: 是否启用智能裁剪
        """
        self.llm_client = llm_client      # 大脑
        self.session = session            # 状态（只读访问）
        self.sandbox = sandbox            # 执行环境
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt

        # 上下文工程
        self._context_engineering = context_engineering
        self._context_window = context_window
        self._enable_pruning = enable_pruning

        # 当前任务（用于智能裁剪）
        self._current_task: str | None = None

        # 执行指标
        self._metrics: list[ToolExecutionMetrics] = []

        logger.info(
            f"Harness initialized: session={session.session_id}, "
            f"max_iterations={max_iterations}, tools={len(sandbox.get_tool_schemas())}, "
            f"context_engineering={context_engineering is not None}"
        )

    # === 核心循环 ===

    async def run_cycle(
        self,
        priority: int = RequestPriority.NORMAL
    ) -> CycleResult:
        """执行一轮对话循环

        核心流程：
        1. 从 Session 拉取上下文（无状态关键）
        2. 调用 LLM 推理
        3. 记录响应到 Session
        4. 如有工具调用，路由到 Sandbox 执行
        5. 记录工具结果到 Session

        Args:
            priority: 请求优先级

        Returns:
            CycleResult: 循环结果
        """
        # 1. 从 Session 构建上下文（关键：无状态）
        context = self._build_context_from_session()

        # 2. 获取工具 schemas
        tools = self.sandbox.get_tool_schemas()

        # 3. 调用 LLM 推理
        response = await self.llm_client.reason(
            context,
            tools=tools,
            priority=priority
        )

        # 4. 解析响应
        choice = response["choices"][0]
        message = choice["message"]

        # 5. 记录 LLM 响应事件
        llm_data: dict[str, Any] = {}
        if message.get("content"):
            llm_data["content"] = message["content"]
        if message.get("tool_calls"):
            llm_data["tool_calls"] = message["tool_calls"]

        self.session.emit_event(EventType.LLM_RESPONSE, llm_data)

        # 6. 处理工具调用或完成
        if message.get("tool_calls"):
            # 路由工具调用到 Sandbox
            tool_results = await self._route_tool_calls(message["tool_calls"])

            # 记录工具结果事件
            for result in tool_results:
                self.session.emit_event(EventType.TOOL_RESULT, {
                    "tool_call_id": result["tool_call_id"],
                    "content": result["content"]
                })

            return {
                "response": response,
                "tool_results": tool_results,
                "continue_loop": True
            }

        # 无工具调用 = 对话完成
        return {
            "response": response,
            "tool_results": None,
            "continue_loop": False
        }

    async def run_conversation(
        self,
        initial_prompt: str,
        priority: int = RequestPriority.CRITICAL
    ) -> str:
        """执行完整对话

        循环直到对话完成或达到上限

        Args:
            initial_prompt: 用户输入
            priority: 请求优先级

        Returns:
            最终响应文本

        Raises:
            MaxIterationsExceeded: 超过最大迭代次数
        """
        # 记录初始输入
        self.session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            logger.debug(f"Harness iteration {iteration}/{self.max_iterations}")

            # 执行一轮循环
            cycle_result = await self.run_cycle(priority)

            if not cycle_result["continue_loop"]:
                # 对话完成
                self.session.record_session_end("completed")
                response = cycle_result["response"]["choices"][0]["message"]
                return response.get("content", "")

        # 超过最大迭代
        self.session.record_session_end("max_iterations_exceeded")
        raise MaxIterationsExceeded(iteration)

    async def stream_conversation(
        self,
        initial_prompt: str,
        priority: int = RequestPriority.CRITICAL
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行对话

        Args:
            initial_prompt: 用户输入
            priority: 请求优先级

        Yields:
            流式响应 chunk:
                - {"type": "chunk", "content": "..."} - 文本片段
                - {"type": "tool_start", "tool_name": "..."} - 工具开始
                - {"type": "tool_end", "result": "..."} - 工具结束
                - {"type": "final", "content": "..."} - 最终响应
                - {"type": "error", "content": "..."} - 错误
        """
        # 记录初始输入
        self.session.emit_event(EventType.USER_INPUT, {"content": initial_prompt})

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 构建上下文
            context = self._build_context_from_session()
            tools = self.sandbox.get_tool_schemas()

            # 流式推理
            full_content = ""
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in self.llm_client.stream_reason(
                context, tools=tools, priority=priority
            ):
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get("tool_calls")
                if tc_list:
                    self._process_tool_delta(tc_list, tool_calls_accumulator)
                    # 发送工具开始通知
                    for tc in tc_list:
                        if tc.get("function", {}).get("name"):
                            yield {
                                "type": "tool_start",
                                "tool_name": tc["function"]["name"]
                            }

            # 累积工具调用
            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator else []
            )

            # 记录响应
            llm_data: dict[str, Any] = {}
            if full_content:
                llm_data["content"] = full_content
            if tool_calls:
                llm_data["tool_calls"] = tool_calls

            self.session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 执行工具或完成
            if tool_calls:
                tool_results = await self._route_tool_calls(tool_calls)
                for result in tool_results:
                    self.session.emit_event(EventType.TOOL_RESULT, {
                        "tool_call_id": result["tool_call_id"],
                        "content": result["content"]
                    })
                    yield {"type": "tool_end", "result": result["content"]}
            else:
                self.session.record_session_end("completed")
                yield {"type": "final", "content": full_content}
                return

        self.session.record_session_end("max_iterations_exceeded")
        raise MaxIterationsExceeded(iteration)

    # === 上下文构建 (上下文工程) ===

    def _build_context_from_session(
        self,
        current_task: str | None = None
    ) -> list[dict[str, Any]]:
        """从 Session 构建优化上下文（上下文工程）

        流程：
        1. 如有 ContextEngineering 实例，使用渐进式压缩 + 智能裁剪
        2. 否则使用 Session 原生方法（摘要标记机制）

        Args:
            current_task: 当前任务描述（用于智能裁剪）

        Returns:
            messages 格式的优化上下文
        """
        if self._context_engineering:
            # 使用上下文工程优化
            return self._context_engineering.build_optimized_context(
                session=self.session,
                context_window=self._context_window,
                current_task=current_task or self._current_task,
                system_prompt=self.system_prompt,
                enable_pruning=self._enable_pruning
            )

        # 无上下文工程时，使用 Session 原生方法
        return self.session.build_context_for_llm(system_prompt=self.system_prompt)

    async def _build_context_from_session_async(
        self,
        current_task: str | None = None,
        enable_semantic_pruning: bool = False
    ) -> list[dict[str, Any]]:
        """异步构建优化上下文（支持 LLM 摘要）

        Args:
            current_task: 当前任务描述
            enable_semantic_pruning: 是否启用语义裁剪（LLM）

        Returns:
            messages 格式的优化上下文
        """
        if self._context_engineering:
            return await self._context_engineering.build_optimized_context_async(
                session=self.session,
                context_window=self._context_window,
                current_task=current_task or self._current_task,
                system_prompt=self.system_prompt,
                enable_pruning=self._enable_pruning,
                enable_semantic_pruning=enable_semantic_pruning
            )

        return self.session.build_context_for_llm(system_prompt=self.system_prompt)

    def set_current_task(self, task: str) -> None:
        """设置当前任务（用于智能裁剪）

        Args:
            task: 当前任务描述
        """
        self._current_task = task
        logger.debug(f"Current task set: {task[:50]}...")

    def _get_events_since_last_summary(self) -> list[dict[str, Any]]:
        """获取最近摘要标记之后的事件"""
        return self.session.get_events_since_last_summary([
            EventType.USER_INPUT,
            EventType.LLM_RESPONSE,
            EventType.TOOL_RESULT
        ])

    # === 工具路由 ===

    async def _route_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """路由工具调用到 Sandbox

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表
        """
        logger.debug(f"Routing {len(tool_calls)} tool calls to Sandbox")

        # 记录工具调用事件
        for tc in tool_calls:
            self.session.emit_event(EventType.TOOL_CALL, {
                "tool_call_id": tc.get("id"),
                "tool_name": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments")
            })

        # 并发执行工具调用
        results = await self._execute_tools_parallel(tool_calls)

        return results

    async def _execute_tools_parallel(
        self,
        tool_calls: list[dict]
    ) -> list[dict[str, Any]]:
        """并发执行工具调用

        Args:
            tool_calls: 工具调用列表

        Returns:
            工具执行结果列表
        """
        # 检查并发写冲突
        conflict_result = self._check_write_conflicts(tool_calls)
        if conflict_result:
            return conflict_result

        # 并发执行
        results = await asyncio.gather(
            *[self._execute_single_tool_with_metrics(tc) for tc in tool_calls],
            return_exceptions=True
        )

        processed_results: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                raise result

            if isinstance(result, BaseException):
                tool_name = tool_calls[i].get("function", {}).get("name", "unknown")
                logger.error(f"Tool {tool_name} failed: {type(result).__name__}: {result}")
                processed_results.append({
                    "tool_call_id": tool_calls[i].get("id", "unknown"),
                    "role": "tool",
                    "content": f"Error: {type(result).__name__}: {str(result)[:200]}"
                })
            elif isinstance(result, dict):
                processed_results.append(result)
            else:
                logger.warning(f"Unexpected result type: {type(result).__name__}")
                processed_results.append({
                    "tool_call_id": tool_calls[i].get("id", "unknown"),
                    "role": "tool",
                    "content": "Error: Unexpected result type"
                })

        return processed_results

    def _check_write_conflicts(self, tool_calls: list[dict]) -> list[dict] | None:
        """检查并发写冲突"""
        write_tools = {"file_write", "file_edit"}
        seen_paths: dict[str, str] = {}

        for tc in tool_calls:
            if tc["function"]["name"] in write_tools:
                try:
                    args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                    path = args.get("path", "")
                    if path:
                        if path in seen_paths:
                            logger.warning(f"Concurrent write conflict: {path}")
                            return [
                                {"role": "tool", "tool_call_id": tc["id"],
                                 "content": f"Error: Concurrent write conflict on '{path}'"}
                                for tc in tool_calls
                            ]
                        seen_paths[path] = tc["id"]
                except Exception as e:
                    logger.debug(f"Failed to parse tool args: {e}")
        return None

    async def _execute_single_tool_with_metrics(
        self,
        tool_call: dict
    ) -> dict[str, Any]:
        """执行单个工具并记录指标"""
        tool_name = tool_call.get("function", {}).get("name", "unknown")
        start_time = time.time()

        # OpenTelemetry Span
        span = self._start_tool_span(tool_name, {})

        try:
            result = await self.sandbox.execute_tools([tool_call])
            duration_ms = (time.time() - start_time) * 1000

            # 记录指标
            self._metrics.append({
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "success": True,
                "error": None
            })

            self._finish_tool_span(span, start_time, success=True)

            return result[0] if result else {
                "tool_call_id": tool_call.get("id"),
                "role": "tool",
                "content": "Error: No result returned"
            }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            self._metrics.append({
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)[:200]
            })

            self._finish_tool_span(span, start_time, success=False, error=e)

            return {
                "tool_call_id": tool_call.get("id"),
                "role": "tool",
                "content": f"Error: {type(e).__name__}: {str(e)[:200]}"
            }

    # === 流式处理辅助 ===

    def _process_tool_delta(self, tc_list: list[dict], accumulator: dict[int, dict]) -> None:
        """处理流式 Tool Call 增量"""
        for tc in tc_list:
            idx = tc.get("index", 0)
            if idx not in accumulator:
                accumulator[idx] = {
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {"name": "", "arguments": ""}
                }
            acc = accumulator[idx]
            if tc.get("id"):
                acc["id"] = tc["id"]
            if tc.get("type"):
                acc["type"] = tc["type"]
            func = tc.get("function", {})
            if func.get("name"):
                acc["function"]["name"] = func["name"]
            if func.get("arguments"):
                acc["function"]["arguments"] += func["arguments"]

    # === OpenTelemetry ===

    def _start_tool_span(self, tool_name: str, tool_args: dict) -> "Span | None":
        """创建工具 Span"""
        tracer = get_tracer()
        if not (tracer and _OBSERVABILITY_ENABLED):
            return None

        span = tracer.start_span(f"{SPAN_TOOL_PREFIX}{tool_name}")
        set_tool_span_attributes(span, tool_name, file_path=tool_args.get("path", ""))
        return span

    def _finish_tool_span(
        self,
        span: "Span | None",
        start_time: float,
        success: bool,
        error: Exception | None = None
    ) -> None:
        """完成 Span"""
        if not span:
            return

        duration_ms = (time.time() - start_time) * 1000
        if success:
            span.set_attribute("seed.tool.duration_ms", duration_ms)
            span.set_status(StatusCode.OK)
        else:
            if error:
                span.record_exception(error)
                span.set_attribute("seed.error.message", str(error)[:500])
                span.set_status(StatusCode.ERROR, str(error)[:200])
        span.end()

    # === 状态恢复 ===

    def replay_to_event(self, target_event_id: int) -> dict[str, Any]:
        """重放到指定事件点"""
        return self.session.replay_to_state(target_event_id)

    def get_current_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return self.session.get_current_state()

    # === 辅助方法 ===

    def get_session_id(self) -> str:
        """获取 Session ID"""
        return self.session.session_id

    def get_event_count(self) -> int:
        """获取事件总数"""
        return self.session.get_event_count()

    def get_metrics(self) -> list[ToolExecutionMetrics]:
        """获取工具执行指标"""
        return self._metrics.copy()

    def clear_metrics(self) -> None:
        """清空指标"""
        self._metrics.clear()

    def get_status(self) -> dict[str, Any]:
        """获取 Harness 状态"""
        return {
            "session_id": self.session.session_id,
            "event_count": self.session.get_event_count(),
            "max_iterations": self.max_iterations,
            "llm_model": self.llm_client.model_id,
            "sandbox_isolation": self.sandbox.isolation_level.value,
            "tools_registered": len(self.sandbox.get_tool_schemas()),
            "metrics_count": len(self._metrics)
        }


class HarnessManager:
    """Harness 管理器 - 支持多实例

    用于管理多个 Harness 实例，支持：
    - 创建新 Harness（牲畜可替换）
    - 销毁 Harness
    - 多实例协作
    - 状态持久化

    使用场景：
    - 多用户并发对话
    - 多任务并行执行
    - 容错恢复
    """

    def __init__(self, gateway_config_path: str):
        """初始化 HarnessManager

        Args:
            gateway_config_path: Gateway 配置文件路径
        """
        self._gateway_config_path = gateway_config_path
        self._harnesses: dict[str, Harness] = {}
        self._sandboxes: dict[str, Sandbox] = {}
        self._gateway: "LLMGateway | None" = None

        logger.info("HarnessManager initialized")

    def _ensure_gateway(self) -> "LLMGateway":
        """确保 Gateway 已创建"""
        if not self._gateway:
            from src.client import LLMGateway
            self._gateway = LLMGateway(self._gateway_config_path)
        return self._gateway

    def create_harness(
        self,
        harness_id: str,
        model_id: str,
        system_prompt: str | None = None,
        sandbox_config: dict[str, Any] | None = None,
        max_iterations: int = MAX_ITERATIONS
    ) -> Harness:
        """创建新的 Harness 实例

        Args:
            harness_id: Harness 实例 ID
            model_id: 模型 ID
            system_prompt: 系统提示
            sandbox_config: Sandbox 配置
            max_iterations: 最大迭代次数

        Returns:
            Harness 实例
        """
        gateway = self._ensure_gateway()

        # 创建 LLMClient
        llm_client = LLMClient(gateway, model_id)

        # 创建 Sandbox
        sandbox_config = sandbox_config or {}
        sandbox = Sandbox(**sandbox_config)

        # 创建 Session
        session = SessionEventStream(harness_id)

        # 创建 Harness
        harness = Harness(
            llm_client, session, sandbox,
            max_iterations=max_iterations,
            system_prompt=system_prompt
        )

        # 注册
        self._harnesses[harness_id] = harness
        self._sandboxes[harness_id] = sandbox

        logger.info(f"Harness created: id={harness_id}, model={model_id}")
        return harness

    def get_harness(self, harness_id: str) -> Harness | None:
        """获取 Harness 实例"""
        return self._harnesses.get(harness_id)

    def destroy_harness(self, harness_id: str) -> bool:
        """销毁 Harness（牲畜可替换）

        Args:
            harness_id: Harness 实例 ID

        Returns:
            是否成功销毁
        """
        if harness_id in self._harnesses:
            harness = self._harnesses[harness_id]
            harness.session.record_session_end("destroyed")
            del self._harnesses[harness_id]

        if harness_id in self._sandboxes:
            sandbox = self._sandboxes[harness_id]
            sandbox.cleanup()
            del self._sandboxes[harness_id]

        logger.info(f"Harness destroyed: id={harness_id}")
        return True

    def list_harnesses(self) -> list[str]:
        """列出所有 Harness ID"""
        return list(self._harnesses.keys())

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """获取所有 Harness 状态"""
        return {
            id: harness.get_status()
            for id, harness in self._harnesses.items()
        }

    def destroy_all(self) -> None:
        """销毁所有 Harness"""
        for harness_id in list(self._harnesses.keys()):
            self.destroy_harness(harness_id)
        logger.info("All harnesses destroyed")

    def get_total_metrics(self) -> dict[str, Any]:
        """获取所有 Harness 的总指标"""
        total_tools = 0
        total_success = 0
        total_failed = 0
        total_duration_ms = 0.0

        for harness in self._harnesses.values():
            metrics = harness.get_metrics()
            total_tools += len(metrics)
            for m in metrics:
                if m["success"]:
                    total_success += 1
                else:
                    total_failed += 1
                total_duration_ms += m["duration_ms"]

        return {
            "total_tool_calls": total_tools,
            "successful_calls": total_success,
            "failed_calls": total_failed,
            "total_duration_ms": total_duration_ms,
            "average_duration_ms": total_duration_ms / total_tools if total_tools > 0 else 0
        }