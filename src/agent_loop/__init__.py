"""
Agent 主循环模块

基于 Harness Engineering "三件套解耦架构" 设计：
- LLMClient (大脑): 负责推理，无状态
- Harness (控制器): 驱动循环，路由工具
- Sandbox (工作台): 隔离执行，安全可控

架构拆分:
- _init.py: 初始化和 Token 管理
- _summarizer.py: 摘要机制
- _skill_tracker.py: Skill outcome 记录
- _observability.py: OpenTelemetry 和状态查询

使用方法:
    from src.agent_loop import AgentLoop
    
    loop = AgentLoop(gateway, model_id="openai/gpt-4")
    result = await loop.run("Hello!")
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from src.abort_signal import AbortController, AbortSignal
from src.builtin_hooks import register_builtin_hooks
from src.client import LLMGateway
from src.context_engineering import CompressionConfig, PruningConfig
from src.harness import MaxIterationsExceededError
from src.lifecycle_hooks import LifecycleHookRegistry, get_global_registry
from src.request_queue import RequestPriority
from src.sandbox import IsolationLevel, Sandbox
from src.security.secure_sandbox import SecureSandbox
from src.session_event_stream import SessionEventStream
from src.tools.ask_user_types import AskUserResult

from ._init import (
    get_context_window,
    get_tokenizer,
    setup_context_engineering,
    setup_harness_trio,
    setup_subsystems,
    setup_tools_and_skills,
)
from ._observability import ObservabilityManager
from ._skill_tracker import SkillTracker
from ._summarizer import Summarizer

logger = logging.getLogger(__name__)

__all__ = ["AgentLoop"]


class AgentLoop:
    """Agent 主循环 - 纯三件套架构 + 上下文工程

    架构设计：
    - LLMClient: 大脑，负责推理
    - Harness: 控制器，驱动循环
    - Sandbox: 工作台，隔离执行
    - SessionEventStream: 状态存储，只追加
    """

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
        """初始化 AgentLoop"""
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval
        self.session_id = session_id or self._generate_session_id()

        # === Session 事件流 ===
        self.session = SessionEventStream(self.session_id)
        self.session.record_session_start({
            "model_id": self.model_id,
            "max_iterations": self.max_iterations,
        })

        # === Token 和上下文窗口 (需要在 _setup_all 之前) ===
        self._encoding = get_tokenizer(self.gateway, self.model_id)
        self.context_window = get_context_window(self.gateway, self.model_id)

        # === 初始化三件套架构 ===
        self._setup_all(
            system_prompt, isolation_level, compression_config, pruning_config,
            enable_pruning, hook_registry, enable_builtin_hooks,
            enable_secure_sandbox, user_permission_level
        )
        
        self._summarizer = Summarizer(
            self.session, self.gateway, self.model_id,
            self.context_window, summary_interval, self._encoding
        )
        
        self._skill_tracker = SkillTracker(self.session, self.session_id)
        
        self._observability = ObservabilityManager(
            self.session, self._hook_registry, self.harness
        )

        # === 取消控制 ===
        self._abort_controller = AbortController()
        self._user_input_event = asyncio.Event()
        self._pending_user_response: AskUserResult | None = None

        # === Scheduler ===
        from src.scheduler import TaskScheduler
        self.scheduler = TaskScheduler(self)

        logger.info(
            f"AgentLoop initialized: model={self.model_id}, "
            f"tools={len(self.tools._tools)}, hooks={self._hook_registry.get_hook_count()}"
        )

    def _get_primary_model(self) -> str:
        """从配置获取主模型"""
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def _generate_session_id(self) -> str:
        """生成会话 ID"""
        from src.tools.memory_tools import _generate_session_filename
        return _generate_session_filename()

    def _setup_all(
        self,
        system_prompt,
        isolation_level,
        compression_config,
        pruning_config,
        enable_pruning,
        hook_registry,
        enable_builtin_hooks,
        enable_secure_sandbox,
        user_permission_level,
    ) -> None:
        """初始化所有子系统"""
        # 工具和技能
        self.tools, self.skill_loader = setup_tools_and_skills()

        # 子系统
        self.subagent_manager, self.system_prompt = setup_subsystems(
            self.gateway, self.model_id, self.skill_loader, system_prompt
        )

        # 钩子
        self._hook_registry = hook_registry or get_global_registry()
        if enable_builtin_hooks and self._hook_registry.get_hook_count() == 0:
            register_builtin_hooks(self._hook_registry)

        # Sandbox
        if enable_secure_sandbox:
            self.sandbox: Sandbox = SecureSandbox(
                isolation_level=isolation_level,
                user_permission_level=user_permission_level,
                enable_progressive_expansion=True,
                enable_single_purpose_tools=True,
            )
        else:
            self.sandbox = Sandbox(isolation_level=isolation_level)
        self.sandbox.register_tools(self.tools)

        # Harness
        self.harness, self.llm_client = setup_harness_trio(
            self.gateway, self.model_id, self.session, self.sandbox,
            self.max_iterations, self.system_prompt, self.context_window,
            enable_pruning, self._hook_registry
        )

        # 上下文工程
        self._context_engineering = setup_context_engineering(
            self.gateway, self.model_id, compression_config, pruning_config, self.harness
        )
        self._compression_config = compression_config
        self._pruning_config = pruning_config
        self._enable_pruning = enable_pruning

    # === 核心执行流程 ===

    async def run(
        self,
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
        self, user_input: str, priority: int = RequestPriority.CRITICAL
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

    async def _handle_user_wait(self, priority: int, signal: AbortSignal) -> None:
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

    # === 用户交互 ===

    def inject_user_input(self, response: AskUserResult) -> None:
        """注入用户响应"""
        self._pending_user_response = response
        self._user_input_event.set()

    def cancel_current_execution(self) -> None:
        """取消当前执行"""
        self._abort_controller.abort(reason="user_interrupt")
        self._user_input_event.set()

    def get_abort_signal(self) -> AbortSignal:
        """获取取消信号"""
        return self._abort_controller.signal

    def set_autonomous_mode(self, enabled: bool, skip_response: str | None = None) -> None:
        """设置自主探索模式"""
        self.harness.set_autonomous_mode(enabled, skip_response)
        logger.info(f"AgentLoop autonomous mode: {enabled}")

    def inject_system_message(self, message: str) -> None:
        """注入系统消息"""
        from src.session_event_stream import EventType
        self.session.emit_event(
            EventType.SYSTEM_MESSAGE,
            {"content": message, "source": "autonomous_budget_warning"},
        )
        logger.info(f"System message injected: {message[:100]}...")

    # === 状态查询 ===

    def get_status(self) -> dict[str, Any]:
        """获取状态"""
        return self._observability.get_status(
            self.session_id, self.model_id,
            self._summarizer._conversation_rounds, self.context_window,
            self.sandbox, self._enable_pruning,
            self._compression_config, self._context_engineering
        )

    def get_hook_registry(self) -> LifecycleHookRegistry | None:
        """获取钩子注册中心"""
        return self._observability.get_hook_registry()

    def get_hook_stats(self) -> dict[str, Any]:
        """获取钩子统计"""
        return self._observability.get_hook_stats()

    def register_custom_hook(
        self, hook_point: str, callback: Callable[..., Any],
        priority: int = 100, name: str | None = None,
    ) -> str | None:
        """注册自定义钩子"""
        return self._observability.register_custom_hook(hook_point, callback, priority, name)

    def replay_to_event(self, event_id: int) -> dict[str, Any]:
        """重放事件"""
        return self._observability.replay_to_event(event_id)

    def get_event_count(self) -> int:
        """获取事件数"""
        return self._observability.get_event_count()

    @property
    def history(self) -> list[dict[str, Any]]:
        """兼容性属性"""
        return self.session.build_context_for_llm(system_prompt=None)

    @property
    def _conversation_rounds(self) -> int:
        """向后兼容属性 - 委托给 _summarizer"""
        return self._summarizer._conversation_rounds


# === 向后兼容导入 (供测试 mock 使用) ===
from src.scheduler import TaskScheduler
from src.subagent_manager import SubagentManager
from src.tools import ToolRegistry
from src.tools.skill_loader import SkillLoader

# 向后兼容别名 (原函数已移动到 memory_tools)
from src.tools.memory_tools import _generate_session_filename

__all__.extend([
    "ToolRegistry", "SkillLoader", "TaskScheduler", "SubagentManager",
    "_generate_session_filename",
])