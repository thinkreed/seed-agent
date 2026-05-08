"""Agent 主循环模块"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortController
from src.builtin_hooks import register_builtin_hooks
from src.client import LLMGateway
from src.context_engineering import CompressionConfig, PruningConfig
from src.lifecycle_hooks import LifecycleHookRegistry, get_global_registry
from src.request_queue import RequestPriority
from src.sandbox import IsolationLevel, Sandbox
from src.security.secure_sandbox import SecureSandbox
from src.session_event_stream import SessionEventStream

from ._execution import ExecutionMixin
from ._init import get_context_window, get_tokenizer, setup_context_engineering, setup_harness_trio, setup_subsystems, setup_tools_and_skills
from ._observability import ObservabilityManager
from ._skill_tracker import SkillTracker
from ._summarizer import Summarizer
from ._user_interaction import UserInteractionMixin

if TYPE_CHECKING:
    from src.tools.ask_user_types import AskUserResult

logger = logging.getLogger(__name__)
__all__ = ["AgentLoop"]


class AgentLoop(ExecutionMixin, UserInteractionMixin):
    """Agent 主循环 - 纯三件套架构 + 上下文工程"""

    def __init__(self, gateway: LLMGateway, model_id: str | None = None, system_prompt: str | None = None, max_iterations: int = 100, summary_interval: int = 10, session_id: str | None = None, isolation_level: IsolationLevel = IsolationLevel.PROCESS, compression_config: CompressionConfig | None = None, pruning_config: PruningConfig | None = None, enable_pruning: bool = True, hook_registry: LifecycleHookRegistry | None = None, enable_builtin_hooks: bool = True, enable_secure_sandbox: bool = True, user_permission_level: str = "normal"):
        self.gateway = gateway
        self.model_id = model_id or self._get_primary_model()
        self.max_iterations = max_iterations
        self.summary_interval = summary_interval
        self.session_id = session_id or self._generate_session_id()
        self._enable_secure_sandbox = enable_secure_sandbox
        self._user_permission_level = user_permission_level
        self.session = SessionEventStream(self.session_id)
        self.session.record_session_start({"model_id": self.model_id, "max_iterations": self.max_iterations})
        self._encoding = get_tokenizer(self.gateway, self.model_id)
        self.context_window = get_context_window(self.gateway, self.model_id)
        self._setup_all(system_prompt, isolation_level, compression_config, pruning_config, enable_pruning, hook_registry, enable_builtin_hooks, enable_secure_sandbox, user_permission_level)
        self._summarizer = Summarizer(self.session, self.gateway, self.model_id, self.context_window, summary_interval, self._encoding)
        self._skill_tracker = SkillTracker(self.session, self.session_id)
        self._observability = ObservabilityManager(self.session, self._hook_registry, self.harness)
        self._abort_controller = AbortController()
        self._user_input_event = asyncio.Event()
        self._pending_user_response: AskUserResult | None = None
        self.scheduler = TaskScheduler(self)
        logger.info(f"AgentLoop initialized: model={self.model_id}, tools={len(self.tools._tools)}, hooks={self._hook_registry.get_hook_count()}")

    def _get_primary_model(self) -> str:
        from src.shared_config import get_primary_model
        return get_primary_model(self.gateway)

    def _generate_session_id(self) -> str: return _generate_session_filename()

    def _setup_all(self, system_prompt, isolation_level, compression_config, pruning_config, enable_pruning, hook_registry, enable_builtin_hooks, enable_secure_sandbox, user_permission_level) -> None:
        self.tools, self.skill_loader = setup_tools_and_skills()
        self.subagent_manager, self.system_prompt = setup_subsystems(self.gateway, self.model_id, self.skill_loader, system_prompt)
        self._hook_registry = hook_registry or get_global_registry()
        if enable_builtin_hooks and self._hook_registry.get_hook_count() == 0: register_builtin_hooks(self._hook_registry)
        if enable_secure_sandbox:
            self.sandbox: Sandbox = SecureSandbox(isolation_level=isolation_level, user_permission_level=user_permission_level, enable_progressive_expansion=True, enable_single_purpose_tools=True)
        else:
            self.sandbox = Sandbox(isolation_level=isolation_level)
        self.sandbox.register_tools(self.tools)
        self.harness, self.llm_client = setup_harness_trio(self.gateway, self.model_id, self.session, self.sandbox, self.max_iterations, self.system_prompt, self.context_window, enable_pruning, self._hook_registry)
        self._context_engineering = setup_context_engineering(self.gateway, self.model_id, compression_config, pruning_config, self.harness)
        self._compression_config = compression_config
        self._pruning_config = pruning_config
        self._enable_pruning = enable_pruning

    # === 状态查询（委托给 ObservabilityManager） ===
    def get_status(self) -> dict[str, Any]: return self._observability.get_status(self.session_id, self.model_id, self._summarizer._conversation_rounds, self.context_window, self.sandbox, self._enable_pruning, self._compression_config, self._context_engineering)
    def get_hook_registry(self) -> LifecycleHookRegistry | None: return self._observability.get_hook_registry()
    def get_hook_stats(self) -> dict[str, Any]: return self._observability.get_hook_stats()
    def register_custom_hook(self, hook_point: str, callback: Any, priority: int = 100, name: str | None = None) -> str | None: return self._observability.register_custom_hook(hook_point, callback, priority, name)
    def replay_to_event(self, event_id: int) -> dict[str, Any]: return self._observability.replay_to_event(event_id)
    def get_current_state(self) -> dict[str, Any]: return self._observability.get_current_state()
    def get_event_count(self) -> int: return self._observability.get_event_count()

    # === 属性 ===
    @property
    def history(self) -> list[dict[str, Any]]: return self.session.build_context_for_llm(system_prompt=None)

    @property
    def _conversation_rounds(self) -> int: return self._summarizer._conversation_rounds


# === 向后兼容导入 ===
from src.scheduler import TaskScheduler
from src.subagent_manager import SubagentManager
from src.tools import ToolRegistry
from src.tools.memory_tools import _generate_session_filename
from src.tools.skill_loader import SkillLoader

__all__.extend(["SkillLoader", "SubagentManager", "TaskScheduler", "ToolRegistry", "_generate_session_filename"])