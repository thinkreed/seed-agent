"""任务执行核心模块

包含 TaskExecutor 类的核心执行逻辑。
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
from src.autonomous._prompt_builder import (
    build_autonomous_prompt,
    extract_task_signals,
)
from src.autonomous._ralph_loop import run_ralph_loop
from src.autonomous._sop_loader import expand_sop_paths, load_sop
from src.autonomous._state_manager import StateManager, TodoCache
from src.ralph_state import check_safety_limits as check_global_safety_limits
from src.session_event_stream import EventType
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

        # 状态管理
        self._state_manager = StateManager()
        self._todo_cache = TodoCache()

        # 四层防御
        self._defense = DefenseState()

        # 配置
        self._config = get_autonomous_config()
        self._seed_dir = get_seed_dir_with_fallback()

        # SOP 内容
        self._sop_content: str | None = load_sop()

    def _get_completion_promise_file(self) -> Path:
        """获取完成标志文件路径"""
        return self._seed_dir / "ralph" / "completion_promise"

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志"""
        return check_completion_promise(self._get_completion_promise_file())

    def _check_safety_limits(self) -> bool:
        """检查安全上限（防止无限循环）"""
        return check_global_safety_limits(
            iteration=self._state_manager.get_iteration_count(),
            max_iterations=RALPH_MAX_ITERATIONS,
            start_time=self._state_manager.get_start_time(),
            accumulated_duration=self._state_manager.get_accumulated_duration(),
            max_duration=RALPH_MAX_DURATION,
        )

    async def execute_autonomous_task(self) -> str | None:
        """执行自主探索任务

        Returns:
            str | None: 探索结果文本，失败时返回 None
        """
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return None

        self._state_manager.load_or_init_state()

        # 获取重试预算
        max_iterations = self._defense.get_retry_budget()
        if max_iterations == 0:
            logger.warning(
                f"Retry count {self._defense.get_retry_count()} exceeds max "
                f"{self._config.max_retry_count}, stopping"
            )
            return None

        self._defense.reset()
        todo_content = self._todo_cache.load_todo_content(self._seed_dir)
        expand_sop_paths(self._sop_content, self._seed_dir)

        prompt = self._build_full_prompt(todo_content)

        self.agent.session.emit_event(
            EventType.SESSION_START,
            {
                "type": "autonomous_exploration",
                "iteration": self._state_manager.get_iteration_count(),
                "retry_count": self._defense.get_retry_count(),
                "max_iterations_budget": max_iterations,
                "todo_status": bool(todo_content),
            },
        )

        logger.info(
            f"Starting autonomous exploration: budget={max_iterations}, "
            f"retry={self._defense.get_retry_count()}"
        )

        original_system_prompt = self.agent.system_prompt
        original_max_iterations = self.agent.max_iterations

        self.agent.set_autonomous_mode(
            enabled=True,
            skip_response=self._config.ask_user_skip_response,
        )

        try:
            self.agent.system_prompt = prompt
            self.agent.max_iterations = max_iterations

            response = await run_ralph_loop(self, max_iterations)

            if response:
                logger.info(
                    f"Autonomous exploration completed, response length: {len(response)}"
                )
                self.agent.session.emit_event(
                    EventType.SESSION_END,
                    {
                        "type": "autonomous_exploration",
                        "reason": "completed",
                        "response_length": len(response),
                        "iterations_used": self._state_manager.get_iteration_count(),
                    },
                )
                self._defense.reset_retry()
                await notify_completion(self, response)
                return response

            self._defense.increment_retry()
            logger.warning(
                f"Autonomous exploration returned empty response, "
                f"retry_count now {self._defense.get_retry_count()}"
            )
            self.agent.session.emit_event(
                EventType.SESSION_END,
                {
                    "type": "autonomous_exploration",
                    "reason": "empty_response",
                    "retry_count": self._defense.get_retry_count(),
                },
            )
            return None

        except Exception as e:
            logger.exception("Autonomous exploration failed")
            self._state_manager.persist_state(str(e))
            self._defense.increment_retry()
            self.agent.session.emit_event(
                EventType.ERROR_OCCURRED,
                {
                    "error_type": "autonomous_exploration_failed",
                    "error_message": str(e)[:500],
                    "retry_count": self._defense.get_retry_count(),
                },
            )
            return None

        finally:
            self.agent.set_autonomous_mode(enabled=False)
            self.agent.system_prompt = original_system_prompt
            self.agent.max_iterations = original_max_iterations

    def _build_full_prompt(self, todo_content: str) -> str:
        """构建完整的自主探索 prompt"""
        base_system_prompt = self.agent.system_prompt or ""

        skills_prompt = ""
        best_skill = None
        gene_slice = None

        skill_loader = getattr(self.agent, "skill_loader", None)
        if skill_loader:
            skills_prompt = skill_loader.get_skills_prompt()
            signals = extract_task_signals(todo_content, bool(todo_content))
            best_skill = skill_loader.select_best_skill(
                signals=signals,
                available_tools=getattr(
                    self.agent.tools, "get_tool_names", lambda: None
                )(),
            )
            if best_skill:
                gene_slice = skill_loader.get_gene_slice(best_skill)

        expanded_sop = expand_sop_paths(self._sop_content or "", self._seed_dir)

        return build_autonomous_prompt(
            base_system_prompt=base_system_prompt,
            skills_prompt=skills_prompt,
            sop_content=expanded_sop,
            todo_content=todo_content,
            has_todo=bool(todo_content),
            seed_dir=self._seed_dir,
            best_skill=best_skill,
            gene_slice=gene_slice,
        )

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