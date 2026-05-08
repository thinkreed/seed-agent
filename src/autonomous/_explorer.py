"""自主探索模块：空闲时根据 SOP 执行自主任务

继承链: AutonomousExplorerDelegates -> AutonomousExplorerCompat -> AutonomousExplorer
"""

import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import _ensure_ralph_dir
from src.shared_config import get_autonomous_config

from ._defense import check_completion_promise
from ._explorer_compat import AutonomousExplorerCompat
from ._idle_monitor import IdleMonitor
from ._sop_loader import get_sop_path, load_sop
from ._task_executor import TaskExecutor

logger = logging.getLogger("seed_agent")


def _get_completion_promise_file() -> Path:
    """获取完成标志文件路径"""
    return _ensure_ralph_dir().parent / "completion_promise"


class AutonomousExplorer(AutonomousExplorerCompat):
    """自主探索执行器 (四层防御: 预算警告/进度检测/时间断路/重试预算)"""

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable[[str], None] | Callable[[str], Coroutine[None, None, None]] | None = None,
    ):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._idle_monitor = IdleMonitor(idle_timeout=get_autonomous_config().idle_timeout_hours * 3600)
        self._task_executor = TaskExecutor(agent_loop, on_explore_complete)
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
            logger.warning(f"SOP file not found: {get_sop_path()} - disabled")
            return
        self._idle_monitor.set_idle_callback(lambda: self._task_executor.execute_autonomous_task())
        await self._idle_monitor.start()
        logger.warning("Autonomous explorer started")

    async def stop(self) -> None:
        """停止空闲监控"""
        await self._idle_monitor.stop()

    # === 防御机制（测试需要）===

    def _check_completion_promise(self) -> bool:
        return check_completion_promise(_get_completion_promise_file())

    def _check_safety_limits(self) -> bool:
        return self._task_executor._check_safety_limits()

    def _get_retry_budget(self) -> int:
        return self._task_executor._defense.get_retry_budget()

    async def _inject_budget_warning(self, current: int, max_budget: int) -> None:
        await self._task_executor._defense.inject_budget_warning(current, max_budget, self.agent)

    def _check_progress_window(self) -> bool:
        return self._task_executor._defense.check_progress_window()

    def _check_time_circuit_breaker(self) -> bool:
        return self._task_executor._defense.check_time_circuit_breaker(self.agent)

    def _reset_defense_state(self) -> None:
        self._task_executor._defense.reset()

    async def _execute_autonomous_task(self) -> str | None:
        return await self._task_executor.execute_autonomous_task()

    async def _run_ralph_loop(self, max_budget: int | None = None) -> str | None:
        return await self._task_executor._run_ralph_loop(max_budget)

    async def _handle_response(self, response: str | None) -> str | None:
        return await self._task_executor._handle_response(response)


async def create_autonomous_explorer(
    agent_loop: "AgentLoop",
    on_explore_complete: Callable[[str], None] | None = None,
) -> AutonomousExplorer:
    """创建并启动自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer