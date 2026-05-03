"""
Agent 主循环模块

基于 Harness Engineering "三件套解耦架构" 设计：
- LLMClient (大脑): 负责推理，无状态
- Harness (控制器): 驱动循环，路由工具
- Sandbox (工作台): 隔离执行，安全可控

生命周期钩子：
- 确定性执行：关键节点自动触发预设动作
- 不依赖模型记忆：由系统确保关键流程执行
- 支持扩展：可动态注册自定义钩子

上下文工程优化：
- 渐进式压缩：最新完整保留 → 稍旧轻量总结 → 更早简短摘要
- 智能裁剪：根据任务相关性过滤不相关历史
- 原始数据不丢失：Session 保留完整历史

Session 宠物哲学：
- Session 是宠物，不可丢失
- 历史只追加，不可修改/截断/清空
- 摘要只创建标记，不修改原数据
- 支持从任意事件点重放状态

Ask User 机制：
- 真正的等待机制（而非字符串标记）
- Harness 检测等待标记后暂停循环
- AgentLoop 等待用户响应注入
- 恢复执行继续循环

取消机制：
- AbortController/AbortSignal 支持任务取消
- 每轮检查取消状态
- Ctrl+C 触发优雅取消

核心流程:
- 接收用户输入 → Harness.run_cycle() → LLM 推理 → Sandbox 执行工具 → 循环
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

import tiktoken

from src.abort_signal import AbortController, AbortSignal
from src.builtin_hooks import register_builtin_hooks
from src.client import LLMGateway
from src.context_engineering import (
    CompressionConfig,
    ContextEngineering,
    PruningConfig,
)
from src.harness import Harness, MaxIterationsExceeded

# 生命周期钩子
from src.lifecycle_hooks import LifecycleHookRegistry, get_global_registry
from src.llm_client import LLMClient

# OpenTelemetry
from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)
from src.request_queue import RequestPriority
from src.sandbox import IsolationLevel, Sandbox
from src.scheduler import TaskScheduler, register_scheduler_tools
from src.security.secure_sandbox import SecureSandbox
from src.session_event_stream import EventType, SessionEventStream
from src.subagent_manager import SubagentManager
from src.tools import ToolRegistry
from src.tools.ask_user_types import AskUserResult
from src.tools.builtin_tools import register_builtin_tools
from src.tools.collaboration_tools import register_tools as register_collaboration_tools
from src.tools.memory_tools import (
    _generate_session_filename,
    _record_skill_outcome,
    _save_session_history,
    register_memory_tools,
)
from src.tools.ralph_tools import register_ralph_tools
from src.tools.skill_loader import SkillLoader, register_skill_tools
from src.tools.subagent_tools import init_subagent_manager, register_subagent_tools

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


class AgentLoop:
    """Agent 主循环 - 纯三件套架构 + 上下文工程

    架构设计：
    - LLMClient: 大脑，负责推理
    - Harness: 控制器，驱动循环
    - Sandbox: 工作台，隔离执行
    - SessionEventStream: 状态存储，只追加
    - ContextEngineering: 上下文工程，渐进式压缩 + 智能裁剪

    特性：
    - 无 legacy 代码，强制使用三件套
    - Session 不可变事件流
    - 摘要标记机制（不截断历史）
    - 上下文工程优化（渐进压缩 + 智能裁剪）
    - OpenTelemetry 可观测性
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
        max_iterations: int = 100,
        summary_interval: int = 10,
        session_id: str | None = None,
        isolation_level: IsolationLevel = IsolationLevel.PROCESS,
        compression_config: CompressionConfig | None = None,
        pruning_config: PruningConfig | None = None,
        enable_pruning: bool = True,
        hook_registry: LifecycleHookRegistry | None = None,
        enable_builtin_hooks: bool = True,
        enable_secure_sandbox: bool = True,
        user_permission_level: str = "normal",
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
            compression_config: 上下文压缩配置
            pruning_config: 上下文裁剪配置
            enable_pruning: 是否启用智能裁剪
            hook_registry: 生命周期钩子注册中心（可选，默认使用全局注册中心）
            enable_builtin_hooks: 是否启用内置钩子（默认 True）
        """
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval
        self.session_id = session_id or _generate_session_filename()

        # === 不可变事件流 ===
        self.session = SessionEventStream(self.session_id)
        self.session.record_session_start(
            {
                "model_id": self.model_id,
                "max_iterations": self.max_iterations,
                "summary_interval": self.summary_interval,
                "isolation_level": isolation_level.value,
                "enable_pruning": enable_pruning,
                "enable_secure_sandbox": enable_secure_sandbox,
                "user_permission_level": user_permission_level,
            }
        )

        # === 内部状态 ===
        self._conversation_rounds: int = 0
        self._pending_skill_outcomes: list[dict] = []
        self._encoding = self._get_tokenizer()

        # === 取消控制 ===
        self._abort_controller: AbortController = AbortController()
        self._user_input_event: asyncio.Event = asyncio.Event()
        self._pending_user_response: AskUserResult | None = None

        # === 上下文窗口管理 ===
        self.context_window = self._get_model_context_window()
        self.context_usage_threshold = 0.75

        # === 上下文工程配置 ===
        self._compression_config = compression_config
        self._pruning_config = pruning_config
        self._enable_pruning = enable_pruning

        # === 安全沙盒配置 ===
        self._enable_secure_sandbox = enable_secure_sandbox
        self._user_permission_level = user_permission_level

        # === 生命周期钩子 ===
        self._hook_registry = hook_registry or get_global_registry()
        if enable_builtin_hooks and self._hook_registry.get_hook_count() == 0:
            register_builtin_hooks(self._hook_registry)

        # === 初始化三件套架构 ===
        self._setup_tools_and_skills()
        self._setup_subsystems(system_prompt)
        self._setup_harness_trio(isolation_level)
        self._setup_context_engineering()

    # === 初始化方法 ===

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model

        return get_primary_model(self.gateway)

    def _setup_tools_and_skills(self) -> None:
        """注册工具并加载技能"""
        self.tools = ToolRegistry()

        register_builtin_tools(self.tools)
        register_memory_tools(self.tools)
        register_skill_tools(self.tools)
        register_scheduler_tools(self.tools)
        register_ralph_tools(self.tools)
        register_subagent_tools(self.tools)
        register_collaboration_tools(self.tools)

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
        self.llm_client = LLMClient(gateway=self.gateway, model_id=self.model_id)

        # 2. Sandbox (工作台) - 根据 enable_secure_sandbox 选择类型
        if self._enable_secure_sandbox:
            self.sandbox: Sandbox = SecureSandbox(
                isolation_level=isolation_level,
                workspace_path=None,
                user_permission_level=self._user_permission_level,
                enable_progressive_expansion=True,
                enable_single_purpose_tools=True,
            )
        else:
            self.sandbox = Sandbox(isolation_level=isolation_level, workspace_path=None)
        self.sandbox.register_tools(self.tools)

        # 3. Harness (控制器) - 不传递 context_engineering，稍后初始化
        self.harness = Harness(
            llm_client=self.llm_client,
            session=self.session,
            sandbox=self.sandbox,
            max_iterations=self.max_iterations,
            system_prompt=self.system_prompt,
            context_window=self.context_window,
            enable_pruning=self._enable_pruning,
            hook_registry=self._hook_registry,
        )

        logger.info(
            f"AgentLoop trio initialized: model={self.model_id}, "
            f"isolation={isolation_level.value}, tools={len(self.tools._tools)}, "
            f"hooks={self._hook_registry.get_hook_count()}, "
            f"secure_sandbox={self._enable_secure_sandbox}, "
            f"user_level={self._user_permission_level}"
        )

    def _setup_context_engineering(self) -> None:
        """初始化上下文工程"""
        self._context_engineering = ContextEngineering(
            gateway=self.gateway,
            model_id=self.model_id,
            compression_config=self._compression_config,
            pruning_config=self._pruning_config,
        )

        # 将 ContextEngineering 实例传递给 Harness
        self.harness._context_engineering = self._context_engineering

        logger.info(
            f"ContextEngineering initialized: "
            f"compression={self._compression_config is not None}, "
            f"pruning={self._enable_pruning}"
        )

    # === Token 管理 ===

    def _get_tokenizer(self) -> tiktoken.Encoding | None:
        """获取 tokenizer (带缓存)"""
        model_name = (
            self.model_id.split("/", 1)[-1] if "/" in self.model_id else self.model_id
        )

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
        messages = self.session.build_context_for_llm(system_prompt=self.system_prompt)
        total = 0

        if self.system_prompt:
            total += self._encode_text(self.system_prompt)

        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._encode_text(content)
            if msg.get("tool_calls"):
                import json

                total += self._encode_text(json.dumps(msg["tool_calls"]))

        return total

    # === 摘要机制 ===

    def _format_events_for_summary(self) -> str:
        """将事件格式化为摘要文本"""
        events = self.session.get_events_since_last_summary(
            [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
        )

        lines = []
        for event in events:
            event_type = event["type"]
            data = event["data"]

            if event_type == EventType.USER_INPUT.value:
                lines.append(f"user: {data.get('content', '')}")
            elif event_type == EventType.LLM_RESPONSE.value:
                content = data.get("content", "")
                if data.get("tool_calls"):
                    tc_names = [
                        tc["function"]["name"]
                        for tc in data["tool_calls"]
                        if tc.get("function")
                    ]
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
                self.model_id, [{"role": "user", "content": prompt}], tools=None
            )
            summary = response["choices"][0]["message"]["content"]
            return summary.strip()
        except Exception as e:
            logger.warning(
                f"Summary generation failed: {type(e).__name__}: {str(e)[:100]}"
            )
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
        return (
            (is_context_full or is_round_limit_reached),
            estimated_tokens,
            is_context_full,
        )

    async def _create_summary_marker(self, is_context_full: bool) -> None:
        """创建摘要标记 (不截断历史)"""
        summary = await self._summarize_events()
        if not summary:
            return

        current_event_id = self.session.get_event_count()
        self.session.create_summary_marker(
            current_event_id, summary, {"is_context_full": is_context_full}
        )

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

    async def run(
        self,
        user_input: str,
        priority: int = RequestPriority.CRITICAL,
        wait_for_user: bool = True,
    ) -> str:
        """执行对话（支持 Ask User 等待）

        Args:
            user_input: 用户输入
            priority: 请求优先级
            wait_for_user: 是否阻塞等待用户响应（默认 True）

        Returns:
            最终响应文本

        注意：
            如果 wait_for_user=False，当遇到 Ask User 时返回特殊字符串
            "[AWAITING_USER_INPUT]" 而非阻塞等待
        """
        self._conversation_rounds += 1

        # 重置取消信号
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal

        try:
            result = await self.harness.run_conversation(user_input, priority, signal)

            # 处理等待状态
            if result["status"] == "waiting_for_user":
                if wait_for_user:
                    # 阻塞等待用户响应
                    await self._user_input_event.wait()

                    # 获取注入的响应
                    user_response = self._pending_user_response
                    assert user_response is not None, (
                        "user_response should be set after wait"
                    )

                    # 清理状态
                    self._user_input_event.clear()
                    self._pending_user_response = None

                    # 恢复执行
                    final_result = await self.harness.resume_with_user_response(
                        user_response, priority, signal
                    )

                    if final_result["status"] == "completed":
                        await self._maybe_summarize()
                        self._evaluate_and_record_skill_outcomes(final_success=True)
                        return final_result["content"]
                    if final_result["status"] == "cancelled":
                        return f"[CANCELLED: {final_result['cancel_reason']}]"
                    # 可能再次等待或其他状态
                    return f"[{final_result['status']}]"
                # 不阻塞，返回等待标记
                return "[AWAITING_USER_INPUT]"

            if result["status"] == "cancelled":
                return f"[CANCELLED: {result['cancel_reason']}]"

            if result["status"] == "completed":
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                return result["content"]

            return f"[{result['status']}]"

        except MaxIterationsExceeded:
            logger.exception("Max iterations exceeded")
            self.session.record_session_end("max_iterations_exceeded")
            raise
        except (RuntimeError, OSError, ValueError, asyncio.CancelledError):
            logger.exception("Agent execution failed")
            self.session.record_session_end("error")
            raise

    async def stream_run(
        self, user_input: str, priority: int = RequestPriority.CRITICAL
    ) -> AsyncGenerator[dict, None]:
        """流式执行对话（支持 Ask User 等待和取消）

        Args:
            user_input: 用户输入
            priority: 请求优先级

        Yields:
            流式响应 chunk:
                - {"type": "chunk", "content": "..."} - 文本片段
                - {"type": "tool_start", "tool_name": "..."} - 工具开始
                - {"type": "tool_end", "result": "..."} - 工具结束
                - {"type": "awaiting_user_input", "request": {...}} - 等待用户输入
                - {"type": "cancelled", "reason": "..."} - 执行取消
                - {"type": "final", "content": "..."} - 最终响应
                - {"type": "error", "content": "..."} - 错误
        """
        self._conversation_rounds += 1

        # 重置取消信号
        self._abort_controller = AbortController()
        signal = self._abort_controller.signal

        try:
            # 执行对话
            result = await self.harness.run_conversation(user_input, priority, signal)

            # 处理等待状态
            if result["status"] == "waiting_for_user":
                # 流式返回等待信息
                yield {
                    "type": "awaiting_user_input",
                    "request": result["pending_request"],
                }

                # 阻塞等待用户响应
                await self._user_input_event.wait()

                # 获取注入的响应
                user_response = self._pending_user_response
                assert user_response is not None, (
                    "user_response should be set after wait"
                )

                # 清理状态
                self._user_input_event.clear()
                self._pending_user_response = None

                # 恢复执行
                final_result = await self.harness.resume_with_user_response(
                    user_response, priority, signal
                )

                if final_result["status"] == "completed":
                    await self._maybe_summarize()
                    self._evaluate_and_record_skill_outcomes(final_success=True)
                    yield {"type": "final", "content": final_result["content"]}
                elif final_result["status"] == "cancelled":
                    yield {"type": "cancelled", "reason": final_result["cancel_reason"]}
                elif final_result["status"] == "waiting_for_user":
                    # 再次等待（递归处理）
                    yield {
                        "type": "awaiting_user_input",
                        "request": final_result["pending_request"],
                    }
                else:
                    yield {
                        "type": "error",
                        "content": f"Unexpected status: {final_result['status']}",
                    }

            elif result["status"] == "cancelled":
                yield {"type": "cancelled", "reason": result["cancel_reason"]}

            elif result["status"] == "completed":
                await self._maybe_summarize()
                self._evaluate_and_record_skill_outcomes(final_success=True)
                yield {"type": "final", "content": result["content"]}

            else:
                yield {
                    "type": "error",
                    "content": f"Unexpected status: {result['status']}",
                }

        except MaxIterationsExceeded as e:
            logger.exception("Max iterations exceeded")
            self.session.record_session_end("max_iterations_exceeded")
            yield {"type": "error", "content": str(e)}
        except (RuntimeError, OSError, ValueError, asyncio.CancelledError) as e:
            logger.exception("Agent execution failed")
            self.session.record_session_end("error")
            yield {"type": "error", "content": str(e)}

    def inject_user_input(self, response: AskUserResult) -> None:
        """注入用户响应（外部调用）

        Args:
            response: 用户响应数据

        用法：
            # 在 main.py 或外部系统调用
            agent.inject_user_input(AskUserResult(
                request_id="abc123",
                responses=[UserResponse(question_id="0", selected=["Yes"])],
            ))
        """
        self._pending_user_response = response
        self._user_input_event.set()

    def cancel_current_execution(self) -> None:
        """取消当前执行"""
        self._abort_controller.abort(reason="user_interrupt")

        # 唤醒用户等待（如果有）
        self._user_input_event.set()

    def get_abort_signal(self) -> AbortSignal:
        """获取当前的取消信号"""
        return self._abort_controller.signal

    # === Skill Outcome 记录 ===

    def _record_load_skill_if_needed(
        self, tool_name: str, tool_args: dict, tool_id: str, content: str, failed: bool
    ) -> None:
        """记录 load_skill 结果"""
        if tool_name == "load_skill":
            self._pending_skill_outcomes.append(
                {
                    "skill_name": tool_args.get("name", ""),
                    "tool_call_id": tool_id,
                    "result": content,
                    "signals": self._extract_signals_from_events(),
                    **({"failed": True} if failed else {}),
                }
            )

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

    def _evaluate_and_record_skill_outcomes(self, final_success: bool) -> None:
        """评估并记录 Skill 执行结果"""
        for outcome in self._pending_skill_outcomes:
            skill_name = outcome.get("skill_name", "")
            if not skill_name:
                continue

            result = outcome.get("result", "")
            failed = outcome.get("failed", False)
            signals = outcome.get("signals", [])

            outcome_status, score = self._evaluate_skill_outcome(
                result, failed, final_success
            )

            _record_skill_outcome(
                skill_name=skill_name,
                outcome=outcome_status,
                score=score,
                signals=signals,
                session_id=self.session_id,
                context=f"Event stream session: {self.session_id}",
            )

        self._pending_skill_outcomes.clear()

    def _evaluate_skill_outcome(
        self, result: str, failed: bool, final_success: bool
    ) -> tuple[str, float]:
        """评估单个 Skill 结果"""
        if failed:
            return "failed", 0.0

        if final_success:
            if "Error:" in result or "error" in result.lower():
                return "partial", 0.5
            return "success", 1.0

        return "partial", 0.7

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
        error: Exception | None = None,
    ) -> None:
        """完成 Span"""
        if not span:
            return

        duration_ms = (time.time() - start_time) * 1000
        if success:
            span.set_attribute("seed.tool.duration_ms", duration_ms)
            span.set_status(StatusCode.OK)
        elif error:
            span.record_exception(error)
            span.set_attribute("seed.error.message", str(error)[:500])
            span.set_status(StatusCode.ERROR, str(error)[:200])
        span.end()

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

    # === 兼容性接口 ===

    @property
    def history(self) -> list[dict[str, Any]]:
        """兼容性属性：从事件流构建消息列表"""
        return self.session.build_context_for_llm(system_prompt=None)

    # === 状态查询 ===

    def get_status(self) -> dict[str, Any]:
        """获取 AgentLoop 状态"""
        return {
            "session_id": self.session_id,
            "model_id": self.model_id,
            "event_count": self.session.get_event_count(),
            "conversation_rounds": self._conversation_rounds,
            "context_window": self.context_window,
            "isolation_level": self.sandbox.isolation_level.value,
            "harness_status": self.harness.get_status(),
            "context_engineering": {
                "enabled": self._context_engineering is not None,
                "pruning_enabled": self._enable_pruning,
                "compression_configured": self._compression_config is not None,
            },
            "hooks": {
                "registry": self._hook_registry is not None,
                "hooks_registered": self._hook_registry.get_hook_count()
                if self._hook_registry
                else 0,
                "hook_reports": len(self.harness.get_hook_reports()),
            },
        }

    def get_hook_registry(self) -> LifecycleHookRegistry | None:
        """获取钩子注册中心"""
        return self._hook_registry

    def get_hook_stats(self) -> dict[str, Any]:
        """获取钩子执行统计"""
        if self._hook_registry:
            return self._hook_registry.get_all_stats()
        return {"global": {}, "hooks": {}}

    def register_custom_hook(
        self,
        hook_point: str,
        callback: Callable[..., Any],
        priority: int = 100,
        name: str | None = None,
    ) -> str | None:
        """注册自定义钩子

        Args:
            hook_point: 钩子节点名称
            callback: 钩子回调函数
            priority: 执行优先级（数值越小越先执行）
            name: 钩子名称

        Returns:
            hook_id: 钩子唯一标识
        """
        if self._hook_registry:
            from src.lifecycle_hooks import HookPoint

            # 尝试转换字符串为 HookPoint
            point: HookPoint | str
            try:
                point = HookPoint(hook_point)
            except ValueError:
                point = hook_point
            result = self._hook_registry.register(
                point, callback, priority=priority, name=name
            )
            # register 返回 str | Callable，直接调用时返回 str
            return result if isinstance(result, str) else None
        return None
