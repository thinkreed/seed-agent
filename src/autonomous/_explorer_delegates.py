"""内部方法委托模块

提供 AutonomousExplorer 的内部方法委托实现。
将不常用的委托方法集中管理，减少主文件行数。

从 _explorer.py 中提取，保持测试兼容性。
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.shared_config import get_seed_dir_with_fallback

from ._defense import check_completion_promise
from ._prompt_builder import (
    build_task_instruction,
    extract_autonomous_prompt_core,
    extract_task_signals,
)
from ._state_manager import extract_critical_context


class AutonomousExplorerDelegates:
    """AutonomousExplorer 内部方法委托 mixin

    提供以下委托方法:
    - 状态管理: _persist_state, _load_or_init_state, _cleanup_state
    - 上下文提取: _extract_critical_context
    - Prompt 构建: _build_autonomous_prompt, _build_task_instruction
    - 信号提取: _extract_task_signals, _extract_autonomous_prompt_core
    - TODO 加载: _load_todo_content
    """

    def _extract_critical_context(self) -> str | None:
        """提取关键上下文"""
        # type: ignore[attr-defined]
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
        return self._task_executor._todo_cache.load_todo_content(
            get_seed_dir_with_fallback()
        )

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt"""
        # has_todo 参数保留但未使用，兼容旧 API
        return self._task_executor._build_full_prompt(todo_content)

    def _extract_task_signals(self, todo_content: str, has_todo: bool) -> list[str]:
        """提取任务信号"""
        return extract_task_signals(todo_content, has_todo)

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令"""
        return build_task_instruction(todo_content, has_todo, get_seed_dir_with_fallback())

    def _extract_autonomous_prompt_core(self, full_prompt: str) -> str:
        """提取 prompt 核心"""
        # type: ignore[attr-defined]
        return extract_autonomous_prompt_core(full_prompt, self._sop_content)


__all__ = ["AutonomousExplorerDelegates"]