"""
Ralph Loop 状态管理模块

提供状态持久化方法。
"""

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.ralph_core import CompletionType, StateManager

logger = logging.getLogger("seed_agent.ralph")


class StatePersistenceMixin:
    """Ralph Loop 状态持久化功能 Mixin"""

    if False:
        _iteration_count: int
        _start_time: float
        _accumulated_duration: float
        _state_file: "Path"
        task_prompt_path: "Path"
        completion_type: "CompletionType"
        _state_manager: "StateManager"
        _safety_checker: Any

    def _load_or_init_state(self) -> None:
        """加载或初始化状态"""
        state = self._state_manager.load_or_init()
        self._iteration_count = state.get("iteration", 0)
        self._accumulated_duration = state.get("accumulated_duration", 0)
        self._start_time = state.get("start_time", time.time())

    def _persist_state(self, response: str) -> None:
        """持久化当前状态"""
        self._state_manager.persist(
            self._iteration_count,
            self._start_time,
            self._accumulated_duration,
            response,
            str(self.task_prompt_path) if self.task_prompt_path else "",
            self.completion_type.value,
        )

    def _cleanup(self) -> None:
        """清理状态文件"""
        self._state_manager.cleanup()

    def _generate_status_report(self) -> str:
        """生成状态报告"""
        return self._safety_checker.generate_status_report(
            str(self.task_prompt_path) if self.task_prompt_path else "",
            self._iteration_count,
            self._start_time,
            self._accumulated_duration,
            self.completion_type.value,
            self._state_file,
        )


__all__ = ["StatePersistenceMixin"]