"""
Ralph Loop 执行流程模块

提供核心执行方法：
- run: 执行 Ralph Loop
- stop: 停止执行
- _reset_context: 上下文重置
- _load_task_prompt: 加载任务 prompt

核心特性：
- 外部验证驱动完成
- 新鲜上下文防漂移
- 状态持久化
"""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.errors import ConfigurationError, ErrorSeverity, SeedAgentError, classify_error
from src.ralph_core import (
    CompletionChecker,
    CompletionType,
    SafetyChecker,
    StateManager,
)

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent.ralph")


class ExecutionMixin:
    """Ralph Loop 执行流程功能 Mixin"""

    if False:  # TYPE_CHECKING 替代
        agent: "AgentLoop"
        completion_type: CompletionType
        completion_criteria: dict | None
        task_prompt_path: Path | None
        on_iteration_complete: Callable | None
        max_iterations: int
        max_duration: int
        context_reset_interval: int
        _iteration_count: int
        _start_time: float
        _accumulated_duration: float
        _state_file: Path
        _is_running: bool
        _completion_checker: CompletionChecker
        _state_manager: StateManager
        _safety_checker: SafetyChecker

    async def run(self) -> str:
        """执行 Ralph Loop"""
        self._is_running = True
        self._start_time = time.time()
        self._iteration_count = 0

        self._state_manager.ensure_dir_exists()
        self._load_or_init_state()

        logger.info(f"Ralph Loop started: {self.task_prompt_path}")

        while self._is_running:
            self._iteration_count += 1

            # 安全检查
            if self._safety_checker.check_limits(
                self._iteration_count, self.max_iterations,
                self._start_time, self._accumulated_duration, self.max_duration,
            ):
                break

            # 上下文重置
            self._reset_context()

            # 加载任务 prompt
            prompt = self._load_task_prompt()

            # 执行一轮 Agent Loop
            try:
                response = await self.agent.run(prompt)
            except ConfigurationError:
                logger.critical(f"Configuration error at iteration {self._iteration_count}")
                self._cleanup()
                raise
            except SeedAgentError as e:
                if e.severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.exception(f"Critical error at iteration {self._iteration_count}")
                    self._cleanup()
                    raise
                logger.warning(f"Recoverable error: {e}")
                response = f"Error: {e!s}"
            except Exception as e:
                _error_type, severity = classify_error(e)
                if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.exception(f"Severe error at iteration {self._iteration_count}")
                    self._cleanup()
                    raise
                logger.warning(f"Agent execution failed: {e}")
                response = f"Error: {e!s}"

            # 持久化状态
            self._persist_state(response)

            # 外部完成验证
            if await self._completion_checker.check_completion(
                self.completion_type, self.completion_criteria
            ):
                logger.info(f"Ralph Loop completed at iteration {self._iteration_count}")
                self._cleanup()
                return "DONE"

            # 回调通知
            if self.on_iteration_complete:
                try:
                    if asyncio.iscoroutinefunction(self.on_iteration_complete):
                        await self.on_iteration_complete(self._iteration_count, response)
                    else:
                        self.on_iteration_complete(self._iteration_count, response)
                except Exception as e:
                    logger.warning(f"Callback failed: {e}")

            await asyncio.sleep(1)

        return self._generate_status_report()

    def stop(self) -> None:
        """停止 Ralph Loop"""
        self._is_running = False
        logger.info(f"Ralph Loop stopped at iteration {self._iteration_count}")

    def _reset_context(self) -> None:
        """重置上下文"""
        preserved = _extract_critical_context(self.agent.history)
        _reset_context(
            self.agent.history, self._iteration_count,
            self.context_reset_interval, preserved,
        )

    def _load_task_prompt(self) -> str:
        """加载任务 prompt"""
        if self.task_prompt_path and self.task_prompt_path.exists():
            try:
                content = self.task_prompt_path.read_text(encoding="utf-8")
                return f"[Ralph Loop 迭代 {self._iteration_count}]\n\n{content}"
            except Exception as e:
                logger.warning(f"Failed to load task prompt: {e}")
        return f"继续执行任务。当前迭代: {self._iteration_count}"


# === 辅助函数 ===


def _extract_critical_context(history: list[Any]) -> str:
    """提取关键上下文"""
    if not history:
        return ""

    preserved = []
    for item in history[-5:]:
        if isinstance(item, dict):
            content = item.get("content", "")
            if content:
                preserved.append(content[:200])

    return "\n".join(preserved)


def _reset_context(
    history: list[Any], iteration: int, reset_interval: int, preserved_context: str,
) -> None:
    """重置上下文"""
    if iteration % reset_interval != 0:
        return

    system_messages = []
    for item in history:
        if isinstance(item, dict) and item.get("role") == "system":
            system_messages.append(item)

    history.clear()
    history.extend(system_messages)

    if preserved_context:
        history.append({
            "role": "system",
            "content": f"[迭代 {iteration} 关键上下文]\n{preserved_context}",
        })


__all__ = ["ExecutionMixin", "_extract_critical_context", "_reset_context"]