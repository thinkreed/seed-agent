"""
Ralph Loop: 长周期确定性任务执行器

模块拆分:
- ralph_loop_core/_execution.py: 执行流程
- ralph_loop_core/_factory.py: 工厂方法
- ralph_loop_core/_state_persistence.py: 状态持久化

核心机制:
1. 外部验证驱动完成
2. 每次迭代新鲜上下文
3. 状态持久于文件系统
4. 防无限循环保护
"""

import logging
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.ralph_core import (
    ITERATION_INTERVAL,
    MAX_DURATION,
    MAX_ITERATIONS,
    CompletionChecker,
    CompletionType,
    SafetyChecker,
    StateManager,
)
from src.ralph_loop_core._execution import ExecutionMixin
from src.ralph_loop_core._factory import FactoryMixin, create_ralph_loop
from src.ralph_loop_core._state_persistence import StatePersistenceMixin
from src.shared_config import get_seed_dir_with_fallback

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent.ralph")


class RalphLoop(ExecutionMixin, FactoryMixin, StatePersistenceMixin):
    """Ralph Loop 执行器

    使用 Mixin 组合拆分后的功能模块。
    """

    def __init__(
        self,
        agent_loop: "AgentLoop",
        completion_type: CompletionType,
        completion_criteria: dict | None = None,
        task_prompt_path: Path | None = None,
        on_iteration_complete: Callable[[int, str], None]
        | Callable[[int, str], Coroutine[Any, Any, None]]
        | None = None,
        max_iterations: int | None = None,
        max_duration: int | None = None,
        context_reset_interval: int | None = None,
    ):
        """初始化 Ralph Loop"""
        self.agent = agent_loop
        self.completion_type = completion_type
        self.completion_criteria = completion_criteria
        self.task_prompt_path = task_prompt_path
        self.on_iteration_complete = on_iteration_complete

        # 可配置的上限
        self.max_iterations = max_iterations or MAX_ITERATIONS
        self.max_duration = max_duration or MAX_DURATION
        self.context_reset_interval = context_reset_interval or ITERATION_INTERVAL

        # 运行状态
        self._iteration_count: int = 0
        self._start_time: float = 0
        self._accumulated_duration: float = 0

        # 状态文件
        state_name = (
            task_prompt_path.stem
            if task_prompt_path
            else f"auto_{uuid.uuid4().hex[:8]}"
        )
        self._state_file: Path = get_seed_dir_with_fallback() / "ralph" / f"task_{state_name}_state.json"
        self._is_running: bool = False

        # 使用拆分模块的组件
        self._completion_checker = CompletionChecker()
        self._state_manager = StateManager(self._state_file)
        self._safety_checker = SafetyChecker()

    # === 向后兼容别名 ===

    def _check_marker_file(self, criteria: dict[str, Any] | None = None) -> bool:
        """向后兼容别名"""
        if criteria is None:
            criteria = self.completion_criteria
        return self._completion_checker._check_marker_file(criteria)

    def _check_file_exists(self, criteria: dict[str, Any] | None = None) -> bool:
        """向后兼容别名"""
        if criteria is None:
            criteria = self.completion_criteria
        return self._completion_checker._check_file_exists(criteria)

    def _parse_test_pass_rate(self, output: str | bytes) -> float:
        """向后兼容别名"""
        return self._completion_checker._parse_test_pass_rate(output)


__all__ = [
    "CompletionType",
    "RalphLoop",
    "create_ralph_loop",
]