"""向后兼容属性模块

继承链: AutonomousExplorerDelegates -> AutonomousExplorerCompat -> AutonomousExplorer
"""

from pathlib import Path
from typing import Any

from ._explorer_delegates import AutonomousExplorerDelegates


class AutonomousExplorerCompat(AutonomousExplorerDelegates):
    """向后兼容属性 mixin，代理到子模块实例"""

    # === IdleMonitor 属性 ===

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

    # === StateManager 属性 ===

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

    # === Defense 属性 ===

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


__all__ = ["AutonomousExplorerCompat"]