"""自主探索模块：空闲时根据 SOP 执行自主任务

重构后架构（子模块化）:
- _idle_monitor: 空闲监控
- _sop_loader: SOP 加载
- _prompt_builder: Prompt 构建
- _task_executor: 任务执行
- _state_manager: 状态管理
- _defense: 四层防御

主文件保留 AutonomousExplorer 类骨架和公共 API。
"""

import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import _ensure_ralph_dir
from src.shared_config import get_autonomous_config, get_seed_dir_with_fallback

from ._defense import check_completion_promise
from ._idle_monitor import IdleMonitor
from ._prompt_builder import build_task_instruction, extract_autonomous_prompt_core
from ._sop_loader import get_sop_path, load_sop
from ._task_executor import TaskExecutor

logger = logging.getLogger("seed_agent")


def _get_completion_promise_file() -> Path:
    """获取完成标志文件路径"""
    return _ensure_ralph_dir().parent / "completion_promise"


class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强 + 四层防御体系)

    多层防御体系：
    - Layer 1: 预算警告注入（70%/90%阈值）
    - Layer 2: 进度检测窗口（空转循环识别）
    - Layer 3: 时间断路器（单任务时间上限）
    - Layer 4: 递减重试预算（失败重试递减）
    - 安全上限: 1000轮 + 8小时
    """

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable[[str], None]
        | Callable[[str], Coroutine[Any, Any, None]]
        | None = None,
    ):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete

        # 组合子模块
        self._idle_monitor = IdleMonitor(
            idle_timeout=get_autonomous_config().idle_timeout_hours * 60 * 60
        )
        self._task_executor = TaskExecutor(agent_loop, on_explore_complete)

        # 配置
        self._config = get_autonomous_config()
        self._sop_content: str | None = load_sop()

    # === 公共 API ===

    def record_activity(self) -> None:
        """记录用户活动时间"""
        self._idle_monitor.record_activity()

    def get_idle_time(self) -> float:
        """获取当前空闲时间（秒）"""
        return self._idle_monitor.get_idle_time()

    async def start(self) -> None:
        """启动空闲监控"""
        if not self._sop_content:
            logger.warning(
                f"SOP file not found: {get_sop_path()} - autonomous exploration disabled"
            )
            return

        async def on_idle():
            return await self._task_executor.execute_autonomous_task()

        self._idle_monitor.set_idle_callback(on_idle)
        await self._idle_monitor.start()
        logger.warning("Autonomous explorer started")

    async def stop(self) -> None:
        """停止空闲监控"""
        await self._idle_monitor.stop()

    # === 状态访问（向后兼容）===

    @property
    def _idle_timeout(self) -> float:
        return self._idle_monitor._idle_timeout

    @property
    def _last_activity(self) -> float:
        return self._idle_monitor._last_activity

    @property
    def _running(self) -> bool:
        return self._idle_monitor._running

    @property
    def _task(self) -> Any:
        return self._idle_monitor._task

    @property
    def _iteration_count(self) -> int:
        return self._task_executor._state_manager.get_iteration_count()

    @_iteration_count.setter
    def _iteration_count(self, value: int) -> None:
        self._task_executor._state_manager.set_iteration_count(value)

    @property
    def _ralph_start_time(self) -> float:
        return self._task_executor._state_manager.get_start_time()

    @_ralph_start_time.setter
    def _ralph_start_time(self, value: float) -> None:
        self._task_executor._state_manager.set_start_time(value)

    @property
    def _accumulated_duration(self) -> float:
        return self._task_executor._state_manager.get_accumulated_duration()

    @_accumulated_duration.setter
    def _accumulated_duration(self, value: float) -> None:
        self._task_executor._state_manager.set_accumulated_duration(value)

    @property
    def _empty_response_count(self) -> int:
        return self._task_executor._state_manager.get_empty_response_count()

    @_empty_response_count.setter
    def _empty_response_count(self, value: int) -> None:
        self._task_executor._state_manager._empty_response_count = value

    @property
    def _state_file(self) -> Path:
        return self._task_executor._state_manager.get_state_file()

    @_state_file.setter
    def _state_file(self, value: Path) -> None:
        self._task_executor._state_manager._state_file = value

    @property
    def _task_start_time(self) -> float:
        return self._task_executor._defense._task_start_time

    @_task_start_time.setter
    def _task_start_time(self, value: float) -> None:
        self._task_executor._defense._task_start_time = value

    @property
    def _action_history(self) -> list[dict[str, Any]]:
        return self._task_executor._defense._action_history

    @_action_history.setter
    def _action_history(self, value: list[dict[str, Any]]) -> None:
        self._task_executor._defense._action_history = value

    @property
    def _retry_count(self) -> int:
        return self._task_executor._defense.get_retry_count()

    @_retry_count.setter
    def _retry_count(self, value: int) -> None:
        self._task_executor._defense._retry_count = value

    @property
    def _budget_warning_sent(self) -> bool:
        return self._task_executor._defense._budget_warning_sent

    @_budget_warning_sent.setter
    def _budget_warning_sent(self, value: bool) -> None:
        self._task_executor._defense._budget_warning_sent = value

    @property
    def _budget_urgent_sent(self) -> bool:
        return self._task_executor._defense._budget_urgent_sent

    @_budget_urgent_sent.setter
    def _budget_urgent_sent(self, value: bool) -> None:
        self._task_executor._defense._budget_urgent_sent = value

    @property
    def _time_warning_sent(self) -> bool:
        return self._task_executor._defense._time_warning_sent

    @_time_warning_sent.setter
    def _time_warning_sent(self, value: bool) -> None:
        self._task_executor._defense._time_warning_sent = value

    def get_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return {
            "iteration_count": self._iteration_count,
            "idle_time": self.get_idle_time(),
            "running": self._running,
            "sop_loaded": self._sop_content is not None,
        }

    # === 内部方法（委托给子模块）===

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志"""
        return check_completion_promise(_get_completion_promise_file())

    def _check_safety_limits(self) -> bool:
        """检查安全上限"""
        return self._task_executor._check_safety_limits()

    def _get_retry_budget(self) -> int:
        """获取重试预算"""
        return self._task_executor._defense.get_retry_budget()

    async def _inject_budget_warning(self, current: int, max_budget: int) -> None:
        """注入预算警告"""
        await self._task_executor._defense.inject_budget_warning(
            current, max_budget, self.agent
        )

    def _check_progress_window(self) -> bool:
        """检查进度窗口"""
        return self._task_executor._defense.check_progress_window()

    def _check_time_circuit_breaker(self) -> bool:
        """检查时间断路器"""
        return self._task_executor._defense.check_time_circuit_breaker(self.agent)

    def _reset_defense_state(self) -> None:
        """重置防御状态"""
        self._task_executor._defense.reset()

    def _extract_critical_context(self) -> str | None:
        """提取关键上下文"""
        from ._state_manager import extract_critical_context
        return extract_critical_context(self.agent.history)

    def _persist_state(self, response: str = "") -> None:
        """持久化状态"""
        self._task_executor._state_manager.persist_state(response)

    def _load_or_init_state(self) -> None:
        """加载或初始化状态"""
        self._task_executor._state_manager.load_or_init_state()

    def _cleanup_state(self) -> None:
        """清理状态"""
        self._task_executor._state_manager.cleanup_state()

    def _load_todo_content(self) -> str:
        """加载 TODO 内容"""
        from src.shared_config import get_seed_dir_with_fallback
        return self._task_executor._todo_cache.load_todo_content(get_seed_dir_with_fallback())

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt"""
        return self._task_executor._build_full_prompt(todo_content)

    def _extract_task_signals(self, todo_content: str, has_todo: bool) -> list[str]:
        """提取任务信号"""
        from ._prompt_builder import extract_task_signals
        return extract_task_signals(todo_content, has_todo)

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令"""
        from src.shared_config import get_seed_dir_with_fallback
        return build_task_instruction(todo_content, has_todo, get_seed_dir_with_fallback())

    def _extract_autonomous_prompt_core(self, full_prompt: str) -> str:
        """提取 prompt 核心"""
        return extract_autonomous_prompt_core(full_prompt, self._sop_content)

    async def _execute_autonomous_task(self) -> str | None:
        """执行自主探索任务"""
        return await self._task_executor.execute_autonomous_task()

    async def _run_ralph_loop(self, max_budget: int | None = None) -> str | None:
        """执行 Ralph Loop"""
        return await self._task_executor._run_ralph_loop(max_budget)

    async def _handle_response(self, response: str | None) -> str | None:
        """处理响应"""
        return await self._task_executor._handle_response(response)


async def create_autonomous_explorer(
    agent_loop: "AgentLoop",
    on_explore_complete: Callable[[str], None] | None = None,
) -> AutonomousExplorer:
    """创建自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer