"""
Agent 主循环模块

基于 Harness Engineering "宠物与牲畜基础设施哲学" 设计：
- Session 是宠物：精心培育、持久保存、不可丢失
- 核心接口：emitEvent() 记录事件、getEvents() 读取事件
- 只追加的日志，天然支持重放和状态恢复

三件套解耦架构 (v2.0):
- LLMClient (大脑): 负责推理，无状态
- Harness (控制器): 驱动循环，路由工具
- Sandbox (工作台): 隔离执行，安全可控

负责:
1. Session 不可变事件流 (只追加日志、摘要标记、状态重放)
2. 工具调用执行 (通过 Sandbox 隔离)
3. 技能加载与匹配 (渐进式披露、Memory Graph 选择)
4. 子代理生命周期管理 (创建、等待、结果聚合)
5. 上下文窗口管理 (摘要触发、Token 估算)

核心流程:
- 接收用户输入 → Harness.run_cycle() → Claude 推理 → Sandbox 执行工具 → 循环
- 摘要只创建标记，不截断历史
- 支持从任意事件点重放状态

OpenTelemetry 嵌入:
- 工具调用 Span (seed.tool.{name})
- Session Span (seed.session)
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, TypedDict

import tiktoken

from src.client import LLMGateway
from src.llm_client import LLMClient
from src.harness import Harness
from src.sandbox import IsolationLevel, Sandbox
from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)
from src.request_queue import RequestPriority
from src.scheduler import TaskScheduler, register_scheduler_tools
from src.session_event_stream import EventType, SessionEventStream
from src.subagent_manager import SubagentManager
from src.tools import ToolRegistry
from src.tools.builtin_tools import register_builtin_tools
from src.tools.memory_tools import (
    _generate_session_filename,
    _record_skill_outcome,
    _save_session_history,
    register_memory_tools,
)
from src.tools.ralph_tools import register_ralph_tools
from src.tools.skill_loader import SkillLoader, register_skill_tools
from src.tools.subagent_tools import init_subagent_manager, register_subagent_tools
from src.tools.utils import parse_tool_arguments

# OpenTelemetry Span 类型导入
try:
    from opentelemetry.trace import Span
    _SPAN_TYPE_AVAILABLE = True
except ImportError:
    Span = None  # type: ignore[misc,assignment]
    _SPAN_TYPE_AVAILABLE = False

# 模块级 encoding 缓存
_ENCODING_CACHE: dict[str, tiktoken.Encoding] = {}

logger = logging.getLogger(__name__)

_OBSERVABILITY_ENABLED = is_observability_enabled()


class ToolResult(TypedDict):
    """工具调用结果类型定义"""
    tool_call_id: str
    role: str
    content: str


class MaxIterationsExceeded(Exception):
    """超过最大迭代次数异常"""
    def __init__(self, message: str) -> None:
        super().__init__(message)


class AgentLoop:
    """Agent 主循环 - 基于 Session 不可变事件流

    Harness Engineering 宠物哲学：
    - Session 是宠物，不可丢失
    - 历史只追加，不可修改/截断/清空
    - 摘要只创建标记，不修改原数据
    - 支持从任意事件点重放状态
    """

    SUMMARY_PROMPT = """请将以下对话历史压缩成简洁的摘要，保留关键信息：
1. 用户的核心需求和意图
2. 已完成的关键操作和结果
3. 重要发现或决策
4. 未完成的任务或待处理事项

对话历史：
{history}

请用简洁的要点形式输出摘要（不超过300字）："""

    def __init__(
        self,
        gateway: LLMGateway,
        model_id: str | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 30,
        summary_interval: int = 10,
        session_id: str | None = None,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        use_harness: bool = True
    ):
        """初始化 AgentLoop

        Args:
            gateway: LLM Gateway 实例
            model_id: 模型 ID (格式: provider/model)
            system_prompt: 系统提示
            max_iterations: 最大迭代次数
            summary_interval: 摘要触发间隔 (对话轮数)
            session_id: 会话 ID (用于事件流持久化)
            isolation_level: Sandbox 隔离级别
            use_harness: 是否使用三件套架构 (默认 True)
        """
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval
        self.session_id = session_id or _generate_session_filename()
        self.use_harness = use_harness

        # === 不可变事件流 (替代可变历史) ===
        self.session = SessionEventStream(self.session_id)
        self.session.record_session_start({
            "model_id": self.model_id,
            "max_iterations": self.max_iterations,
            "summary_interval": self.summary_interval,
            "isolation_level": isolation_level.value
        })

        # === 内部状态 ===
        self._conversation_rounds: int = 0
        self._pending_skill_outcomes: list[dict] = []
        self._pending_user_input: str | None = None
        self._encoding = self._get_tokenizer()

        # === 上下文窗口管理 ===
        self.context_window = self._get_model_context_window()
        self.context_usage_threshold = 0.75

        # === 初始化子系统 ===
        self._setup_tools_and_skills()
        self._setup_subsystems(system_prompt)

        # === 三件套架构初始化 ===
        if use_harness:
            self._setup_harness_trio(isolation_level)

    def _setup_tools_and_skills(self) -> None:
        """注册工具并加载技能"""
        self.tools = ToolRegistry()

        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)
        register_skill_tools(self.tools)
        register_scheduler_tools(self.tools)
        register_ralph_tools(self.tools)
        register_subagent_tools(self.tools)

        self.skill_loader = SkillLoader()
        self._available_tools: set[str] = set()

    def _setup_subsystems(self, system_prompt: str | None = None) -> None:
        """初始化子系统"""
        self.subagent_manager = SubagentManager(
            gateway=self.gateway,
            model_id=self.model_id,
        )
        init_subagent_manager(self.subagent_manager)

        self.scheduler = TaskScheduler(self)

        skills_prompt = self.skill_loader.get_skills_prompt()
        if system_prompt:
            self.system_prompt = system_prompt + "\n\n" + skills_prompt
        else:
            self.system_prompt = skills_prompt

    def _setup_harness_trio(self, isolation_level: IsolationLevel) -> None:
        """初始化三件套架构

        Args:
            isolation_level: Sandbox 隔离级别
        """
        # 1. LLMClient (大脑)
        self.llm_client = LLMClient(
            gateway=self.gateway,
            model_id=self.model_id
        )

        # 2. Sandbox (工作台)
        self.sandbox = Sandbox(
            isolation_level=isolation_level,
            workspace_path=None  # 使用当前工作目录
        )
        # 将已注册的工具注入 Sandbox
        self.sandbox.register_tools(self.tools)

        # 3. Harness (控制器)
        self.harness = Harness(
            llm_client=self.llm_client,
            session=self.session,
            sandbox=self.sandbox,
            max_iterations=self.max_iterations,
            system_prompt=self.system_prompt
        )

        logger.info(
            f"Harness trio initialized: model={self.model_id}, "
            f"isolation={isolation_level.value}, tools={len(self.tools._tools)}"
        )

    # === Token 管理 ===

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        return self.gateway.config.agents["defaults"].defaults.primary

    def _get_tokenizer(self) -> tiktoken.Encoding | None:
        """获取 tokenizer (带缓存)"""
        model_name = self.model_id.split("/", 1)[-1] if "/" in self.model_id else self.model_id

        if model_name in _ENCODING_CACHE:
            return _ENCODING_CACHE[model_name]

        try:
            encoding = tiktoken.encoding_for_model(model_name)
            _ENCODING_CACHE[model_name] = encoding
            return encoding
        except KeyError:
            for enc_name in ["cl100k_base", "p50k_base", "r50k_base"]:
                if enc_name in _ENCODING_CACHE:
                    return _ENCODING_CACHE[enc_name]
                try:
                    encoding = tiktoken.get_encoding(enc_name)
                    _ENCODING_CACHE[enc_name] = encoding
                    return encoding
                except KeyError:
                    continue
            return None

    def _get_model_context_window(self) -> int:
        """获取模型上下文窗口大小"""
        if "/" in self.model_id:
            provider_id, model_id = self.model_id.split("/", 1)
            provider = self.gateway.config.models.get(provider_id)
            if provider:
                for m in provider.models:
                    if m.id == model_id:
                        return m.contextWindow
        return 100000

    def _encode_text(self, text: str) -> int:
        """编码文本返回 token 数"""
        if self._encoding:
            return len(self._encoding.encode(text))
        return int(len(text) * 0.7)

    def _estimate_context_size(self) -> int:
        """估算当前上下文 Token 数"""
        # 从事件流构建当前上下文并估算
        messages = self.session.build_context_for_llm(system_prompt=self.system_prompt)
        total = 0

        if self.system_prompt:
            total += self._encode_text(self.system_prompt)

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._encode_text(content)
            if msg.get("tool_calls"):
                total += self._encode_text(json.dumps(msg["tool_calls"]))

        return total

    # === 上下文构建 ===

    def _build_messages(self) -> list[dict]:
        """从事件流构建消息列表"""
        return self.session.build_context_for_llm(system_prompt=self.system_prompt)

    # === 摘要机制 (不截断历史) ===

    def _format_events_for_summary(self) -> str:
        """将事件格式化为摘要文本"""
        # 获取最近摘要之后的事件
        events = self.session.get_events_since_last_summary([
            EventType.USER_INPUT,
            EventType.LLM_RESPONSE,
            EventType.TOOL_RESULT
        ])

        lines = []
        for event in events:
            event_type = event["type"]
            data = event["data"]

            if event_type == EventType.USER_INPUT.value:
                lines.append(f"user: {data.get('content', '')}")
            elif event_type == EventType.LLM_RESPONSE.value:
                content = data.get("content", "")
                if data.get("tool_calls"):
                    tc_names = [tc["function"]["name"] for tc in data["tool_calls"] if tc.get("function")]
                    content = f"[Tool Calls: {', '.join(tc_names)}]"
                if content:
                    lines.append(f"assistant: {content}")
            elif event_type == EventType.TOOL_RESULT.value:
                content = data.get("content", "")[:200]
                lines.append(f"tool: {content}")

        return "\n".join(lines)

    async def _summarize_events(self) -> str | None:
        """使用 LLM 总结事件流"""
        events_text = self._format_events_for_summary()
        if not events_text:
            return None

        prompt = self.SUMMARY_PROMPT.format(history=events_text)
        try:
            response = await self.gateway.chat_completion(
                self.model_id,
                [{"role": "user", "content": prompt}],
                tools=None
            )
            summary = response["choices"][0]["message"]["content"]
            return summary.strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {type(e).__name__}: {str(e)[:100]}")
            return None

    def _should_summarize(self) -> tuple[bool, int, bool]:
        """检查是否需要摘要

        Returns:
            (should_summarize, estimated_tokens, is_context_full)
        """
        estimated_tokens = self._estimate_context_size()
        token_threshold = self.context_window * self.context_usage_threshold
        is_context_full = estimated_tokens > token_threshold
        is_round_limit_reached = self._conversation_rounds >= self.summary_interval
        return (is_context_full or is_round_limit_reached), estimated_tokens, is_context_full

    async def _create_summary_marker(self, is_context_full: bool) -> None:
        """创建摘要标记 (不截断历史)"""
        summary = await self._summarize_events()
        if not summary:
            return

        # 记录摘要事件
        self.session.emit_event(EventType.SUMMARY_GENERATED, {
            "summary": summary,
            "is_context_full": is_context_full
        })

        # 创建摘要标记
        current_event_id = self.session.get_event_count()
        self.session.create_summary_marker(
            current_event_id,
            summary,
            {"is_context_full": is_context_full}
        )

        # 持久化摘要到 L4
        _save_session_history([], summary=summary, session_id=self.session_id)

        self._conversation_rounds = 0
        logger.info(f"Summary marker created: covers events 1-{current_event_id}")

    async def _maybe_summarize(self) -> None:
        """检查并执行摘要"""
        needs_summary, estimated_tokens, is_context_full = self._should_summarize()
        if not needs_summary:
            return

        logger.info(
            f"Summary triggered: tokens={estimated_tokens}/{self.context_window}, "
            f"rounds={self._conversation_rounds}/{self.summary_interval}"
        )

        await self._create_summary_marker(is_context_full)

    # === 核心执行流程 ===

    async def run(self, user_input: str, priority: int = RequestPriority.CRITICAL) -> str:
        """执行对话

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Returns:
            最终响应文本
        """
        # 使用 Harness 执行（三件套架构）
        if self.use_harness and hasattr(self, 'harness'):
            return await self._run_with_harness(user_input, priority)

        # 传统执行流程（向后兼容）
        return await self._run_legacy(user_input, priority)

    async def _run_with_harness(self, user_input: str, priority: int) -> str:
        """使用 Harness 执行对话（三件套架构）

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Returns:
            最终响应文本
        """
        self._conversation_rounds += 1

        try:
            result = await self.harness.run_conversation(user_input, priority)

            # 执行摘要和技能记录
            await self._maybe_summarize()
            self._evaluate_and_record_skill_outcomes(final_success=True)

            return result

        except Exception as e:
            if "max_iterations" in str(e).lower():
                raise MaxIterationsExceeded(str(e))
            raise

    async def _run_legacy(self, user_input: str, priority: int) -> str:
        """传统执行流程（向后兼容）

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Returns:
            最终响应文本
        """
        # 1. 记录用户输入事件
        self.session.emit_event(EventType.USER_INPUT, {"content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 2. 处理中断输入
            if self._pending_user_input:
                pending = self._pending_user_input
                self._pending_user_input = None
                self.session.emit_event(EventType.USER_INPUT, {"content": pending})
                self._conversation_rounds += 1
                iteration = 0
                continue

            # 3. 构建上下文并调用 LLM
            messages = self._build_messages()
            response = await self.gateway.chat_completion(
                self.model_id,
                messages,
                priority=priority,
                tools=self.tools.get_schemas()
            )

            # 4. 处理响应
            choice = response["choices"][0]
            message = choice["message"]

            # 记录 LLM 响应事件
            llm_data: dict[str, Any] = {}
            if message.get("content"):
                llm_data["content"] = message["content"]
            if message.get("tool_calls"):
                llm_data["tool_calls"] = message["tool_calls"]

            self.session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 5. 执行工具调用或返回
            if message.get("tool_calls"):
                tool_results = await self._execute_tool_calls(message["tool_calls"])
                # 记录工具结果事件
                for result in tool_results:
                    self.session.emit_event(EventType.TOOL_RESULT, {
                        "tool_call_id": result["tool_call_id"],
                        "content": result["content"]
                    })
                # 继续循环
            else:
                # 对话完成
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                self.session.record_session_end("completed")
                return message.get("content", "")

        self.session.record_session_end("max_iterations_exceeded")
        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )

    async def stream_run(
        self,
        user_input: str,
        priority: int = RequestPriority.CRITICAL
    ) -> AsyncGenerator[dict, None]:
        """流式执行对话

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Yields:
            流式响应 chunk
        """
        # 使用 Harness 执行（三件套架构）
        if self.use_harness and hasattr(self, 'harness'):
            async for chunk in self._stream_run_with_harness(user_input, priority):
                yield chunk
            return

        # 传统执行流程（向后兼容）
        async for chunk in self._stream_run_legacy(user_input, priority):
            yield chunk

    async def _stream_run_with_harness(
        self,
        user_input: str,
        priority: int
    ) -> AsyncGenerator[dict, None]:
        """使用 Harness 流式执行对话（三件套架构）

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Yields:
            流式响应 chunk
        """
        self._conversation_rounds += 1

        try:
            async for chunk in self.harness.stream_conversation(user_input, priority):
                yield chunk

            # 执行摘要和技能记录
            await self._maybe_summarize()
            self._evaluate_and_record_skill_outcomes(final_success=True)

        except Exception as e:
            if "max_iterations" in str(e).lower():
                raise MaxIterationsExceeded(str(e))
            raise

    async def _stream_run_legacy(
        self,
        user_input: str,
        priority: int
    ) -> AsyncGenerator[dict, None]:
        """传统流式执行流程（向后兼容）"""
        # 1. 记录用户输入事件
        self.session.emit_event(EventType.USER_INPUT, {"content": user_input})
        self._conversation_rounds += 1

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # 2. 处理中断输入
            if self._pending_user_input:
                pending = self._pending_user_input
                self._pending_user_input = None
                self.session.emit_event(EventType.USER_INPUT, {"content": pending})
                self._conversation_rounds += 1
                iteration = 0
                continue

            # 3. 流式调用 LLM
            messages = self._build_messages()
            full_content = ""
            tool_calls_accumulator: dict[int, dict] = {}

            async for chunk in self.gateway.stream_chat_completion(
                self.model_id, messages, priority=priority, tools=self.tools.get_schemas()
            ):
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    full_content += content
                    yield {"type": "chunk", "content": content}

                tc_list = delta.get("tool_calls")
                if tc_list:
                    self._process_tool_delta(tc_list, tool_calls_accumulator)

            # 4. 累积工具调用
            tool_calls = (
                [tool_calls_accumulator[i] for i in sorted(tool_calls_accumulator.keys())]
                if tool_calls_accumulator else []
            )

            # 5. 记录 LLM 响应事件
            llm_data: dict[str, Any] = {}
            if full_content:
                llm_data["content"] = full_content
            if tool_calls:
                llm_data["tool_calls"] = tool_calls

            self.session.emit_event(EventType.LLM_RESPONSE, llm_data)

            # 6. 执行工具或完成
            if tool_calls:
                tool_results = await self._execute_tool_calls(tool_calls)
                for result in tool_results:
                    self.session.emit_event(EventType.TOOL_RESULT, {
                        "tool_call_id": result["tool_call_id"],
                        "content": result["content"]
                    })
            else:
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                self.session.record_session_end("completed")
                yield {"type": "final", "content": full_content}
                return

        self.session.record_session_end("max_iterations_exceeded")
        raise MaxIterationsExceeded(
            f"Agent exceeded maximum iterations ({self.max_iterations})"
        )

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

    # === 工具执行 ===

    def _check_write_conflicts(self, tool_calls: list[dict]) -> list[dict] | None:
        """检查并发写冲突"""
        write_tools = {"file_write", "file_edit"}
        seen_paths = {}

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

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict[str, Any]]:
        """批量执行工具调用"""
        conflict_result = self._check_write_conflicts(tool_calls)
        if conflict_result:
            return conflict_result

        results = await asyncio.gather(
            *[self._run_single_tool_call(tc) for tc in tool_calls],
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

    async def _run_single_tool_call(self, tool_call: dict) -> dict:
        """执行单个工具调用"""
        tool_id = tool_call["id"]
        tool_name = tool_call["function"]["name"]
        tool_args = parse_tool_arguments(tool_call["function"]["arguments"])

        span = self._start_tool_span(tool_name, tool_args)
        start_time = time.time()

        try:
            result = await self.tools.execute(tool_name, **tool_args)
            self._finish_tool_span(span, start_time, success=True)

            # 记录工具调用事件
            self.session.emit_event(EventType.TOOL_CALL, {
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "arguments": tool_args
            })

            self._record_load_skill_if_needed(tool_name, tool_args, tool_id, str(result), failed=False)

            return {"role": "tool", "tool_call_id": tool_id, "content": str(result)}

        except Exception as e:
            self._finish_tool_span(span, start_time, success=False, error=e)

            self.session.emit_event(EventType.ERROR_OCCURRED, {
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
                "tool_name": tool_name,
                "tool_call_id": tool_id
            })

            self._record_load_skill_if_needed(tool_name, tool_args, tool_id, f"Error: {e!s}", failed=True)

            return {"role": "tool", "tool_call_id": tool_id, "content": f"Error: {e!s}"}

    def _record_load_skill_if_needed(
        self,
        tool_name: str,
        tool_args: dict,
        tool_id: str,
        content: str,
        failed: bool
    ) -> None:
        """记录 load_skill 结果"""
        if tool_name == "load_skill":
            self._pending_skill_outcomes.append({
                "skill_name": tool_args.get("name", ""),
                "tool_call_id": tool_id,
                "result": content,
                "signals": self._extract_signals_from_events(),
                **({"failed": True} if failed else {})
            })

    def _extract_signals_from_events(self) -> list[str]:
        """从最近事件提取触发信号"""
        signals = []
        recent_events = self.session.get_events(start_id=-5)

        for event in recent_events:
            if event["type"] == EventType.USER_INPUT.value:
                content = event["data"].get("content", "")
                if content:
                    words = content.split()[:5]
                    signals.extend(words)

        return signals[:10]

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

    # === Memory Graph ===

    def _evaluate_and_record_skill_outcomes(self, final_success: bool) -> None:
        """评估并记录 Skill 执行结果"""
        for outcome in self._pending_skill_outcomes:
            skill_name = outcome.get("skill_name", "")
            if not skill_name:
                continue

            result = outcome.get("result", "")
            failed = outcome.get("failed", False)
            signals = outcome.get("signals", [])

            outcome_status, score = self._evaluate_skill_outcome(result, failed, final_success)

            _record_skill_outcome(
                skill_name=skill_name,
                outcome=outcome_status,
                score=score,
                signals=signals,
                session_id=self.session_id,
                context=f"Event stream session: {self.session_id}"
            )

        self._pending_skill_outcomes.clear()

    def _evaluate_skill_outcome(
        self,
        result: str,
        failed: bool,
        final_success: bool
    ) -> tuple[str, float]:
        """评估单个 Skill 结果"""
        if failed:
            return "failed", 0.0

        if final_success:
            if "Error:" in result or "error" in result.lower():
                return "partial", 0.5
            return "success", 1.0

        return "partial", 0.7

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

    # === 兼容性接口 (供外部调用) ===

    @property
    def history(self) -> list[dict[str, Any]]:
        """兼容性属性：从事件流构建消息列表"""
        return self.session.build_context_for_llm(system_prompt=None)