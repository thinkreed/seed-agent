"""任务执行核心模块

包含 TaskExecutor 类定义和基本方法。
"""

import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.autonomous._defense import DefenseState, check_completion_promise
from src.autonomous._executor_constants import RALPH_MAX_DURATION, RALPH_MAX_ITERATIONS
from src.autonomous._executor_helpers import (
    handle_response,
    notify_completion,
    record_tool_calls,
    reset_context_if_needed,
)
from src.autonomous._executor_task import build_full_prompt, execute_autonomous_task
from src.autonomous._ralph_checks import check_safety_limits
from src.autonomous._sop_loader import load_sop
from src.autonomous._state_manager import StateManager, TodoCache
from src.shared_config import get_autonomous_config, get_seed_dir_with_fallback

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")


class TaskExecutor:
    """任务执行器

    执行自主探索任务，包含 Ralph Loop 主循环和四层防御体系。
    """

    def __init__(
        self,
        agent: "AgentLoop",
        on_explore_complete: Callable[[str], None]
        | Callable[[str], Coroutine[Any, Any, None]]
        | None = None,
    ):
        """初始化任务执行器

        Args:
            agent: AgentLoop 实例
            on_explore_complete: 探索完成回调
        """
        self.agent = agent
        self.on_explore_complete = on_explore_complete

        self._state_manager = StateManager()
        self._todo_cache = TodoCache()
        self._defense = DefenseState()
        self._config = get_autonomous_config()
        self._seed_dir = get_seed_dir_with_fallback()
        self._sop_content: str | None = load_sop()

    def _get_completion_promise_file(self) -> Path:
        """获取完成标志文件路径"""
        return self._seed_dir / "ralph" / "completion_promise"

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志"""
        return check_completion_promise(self._get_completion_promise_file())

    def _check_safety_limits_internal(self) -> bool:
        """检查安全上限"""
        return check_safety_limits(self)

    def _check_safety_limits(self) -> bool:
        """检查安全上限（向后兼容别名）"""
        return self._check_safety_limits_internal()

    async def execute_autonomous_task(self) -> str | None:
        """执行自主探索任务"""
        return await execute_autonomous_task(
            agent=self.agent,
            state_manager=self._state_manager,
            todo_cache=self._todo_cache,
            defense=self._defense,
            sop_content=self._sop_content,
            seed_dir=self._seed_dir,
            config=self._config,
            on_explore_complete=self.on_explore_complete,
        )

    def _build_full_prompt(self, todo_content: str) -> str:
        """构建完整的自主探索 prompt"""
        return build_full_prompt(self.agent, self._sop_content, todo_content, self._seed_dir)

    # 辅助方法委托
    async def _reset_context_if_needed(self) -> str | None:
        return await reset_context_if_needed(self)

    async def _handle_response(self, response: str | None) -> str | None:
        return await handle_response(self, response)

    async def _notify_completion(self, result: str) -> None:
        await notify_completion(self, result)

    def _record_tool_calls(self) -> None:
        record_tool_calls(self)


__all__ = ["TaskExecutor"]