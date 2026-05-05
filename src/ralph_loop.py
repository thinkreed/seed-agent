"""
Ralph Loop: 长周期确定性任务执行器

核心机制:
1. 外部验证驱动完成 - 由客观标准（测试/DONE标志）决定，而非模型自判
2. 每次迭代新鲜上下文 - 消除上下文漂移风险
3. 状态持久于文件系统 - 任务可恢复（进程崩溃后继续）
4. 防无限循环保护 - 迭代上限+时间上限双重保护

重构说明：
- 类型定义移至 ralph_core/_types.py
- 完成验证移至 ralph_core/_completion.py
- 状态管理移至 ralph_core/_state.py
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.ralph_core import (
    CompletionChecker,
    CompletionType,
    ITERATION_INTERVAL,
    MAX_DURATION,
    MAX_ITERATIONS,
    SafetyChecker,
    StateManager,
)
from src.errors import ConfigurationError, ErrorSeverity, SeedAgentError, classify_error
from src.shared_config import get_seed_dir_with_fallback

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent.ralph")


def _extract_critical_context(history: list[Any]) -> str:
    """提取关键上下文"""
    # 简化实现：取最近的几条消息
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
    history: list[Any],
    iteration: int,
    reset_interval: int,
    preserved_context: str,
) -> None:
    """重置上下文"""
    if iteration % reset_interval != 0:
        return

    # 保留系统消息和关键上下文
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


class RalphLoop:
    """Ralph Loop 执行器"""

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

    # === 核心方法 ===

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

            # 1. 安全检查
            if self._safety_checker.check_limits(
                self._iteration_count,
                self.max_iterations,
                self._start_time,
                self._accumulated_duration,
                self.max_duration,
            ):
                break

            # 2. 上下文重置
            self._reset_context()

            # 3. 加载任务 prompt
            prompt = self._load_task_prompt()

            # 4. 执行一轮 Agent Loop
            try:
                response = await self.agent.run(prompt)
            except ConfigurationError as e:
                logger.critical(f"Configuration error at iteration {self._iteration_count}: {e}")
                self._cleanup()
                raise
            except SeedAgentError as e:
                error_type, severity = e.error_type, e.severity
                if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.exception(f"Critical error at iteration {self._iteration_count}")
                    self._cleanup()
                    raise
                logger.warning(f"Recoverable error at iteration {self._iteration_count}: {e}")
                response = f"Error: {e!s}"
            except Exception as e:
                error_type, severity = classify_error(e)
                if severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
                    logger.exception(f"Severe unclassified error at iteration {self._iteration_count}")
                    self._cleanup()
                    raise
                logger.warning(f"Agent execution failed: {e}")
                response = f"Error: {e!s}"

            # 5. 持久化状态
            self._persist_state(response)

            # 6. 外部完成验证
            if await self._completion_checker.check_completion(
                self.completion_type, self.completion_criteria
            ):
                logger.info(f"Ralph Loop completed at iteration {self._iteration_count}")
                self._cleanup()
                return "DONE"

            # 7. 回调通知
            if self.on_iteration_complete:
                try:
                    if asyncio.iscoroutinefunction(self.on_iteration_complete):
                        await self.on_iteration_complete(self._iteration_count, response)
                    else:
                        self.on_iteration_complete(self._iteration_count, response)
                except Exception as e:
                    logger.warning(f"Callback failed: {e}")

            # 8. 等待下一轮
            await asyncio.sleep(1)

        return self._generate_status_report()

    def stop(self) -> None:
        """停止 Ralph Loop"""
        self._is_running = False
        logger.info(f"Ralph Loop stopped at iteration {self._iteration_count}")

    # === 上下文管理 ===

    def _reset_context(self) -> None:
        """重置上下文"""
        preserved = _extract_critical_context(self.agent.history)
        _reset_context(
            self.agent.history,
            self._iteration_count,
            self.context_reset_interval,
            preserved,
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

    # === 状态持久化 ===

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

    # === 辅助方法 ===

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

    # === 工厂方法 ===

    @classmethod
    def create_test_driven(
        cls,
        agent_loop,
        task_prompt_path: Path,
        test_command: str = "pytest tests/ -v",
        pass_rate: float = 100,
    ) -> "RalphLoop":
        """创建测试驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.TEST_PASS,
            completion_criteria={"test_command": test_command, "pass_rate": pass_rate},
            task_prompt_path=task_prompt_path,
        )

    @classmethod
    def create_marker_driven(
        cls,
        agent_loop,
        task_prompt_path: Path,
        marker_path: Path | None = None,
        marker_content: str = "DONE",
    ) -> "RalphLoop":
        """创建标志文件驱动的 Ralph Loop"""
        return cls(
            agent_loop=agent_loop,
            completion_type=CompletionType.MARKER_FILE,
            completion_criteria={
                "marker_path": str(marker_path or get_seed_dir_with_fallback() / "completion_marker"),
                "marker_content": marker_content,
            },
            task_prompt_path=task_prompt_path,
        )


async def create_ralph_loop(
    agent_loop,
    task_file: str,
    completion_type: str = "marker_file",
    completion_criteria: dict | None = None,
    **kwargs,
) -> RalphLoop:
    """创建 Ralph Loop 实例"""
    type_map = {
        "test_pass": CompletionType.TEST_PASS,
        "file_exists": CompletionType.FILE_EXISTS,
        "marker_file": CompletionType.MARKER_FILE,
        "git_clean": CompletionType.GIT_CLEAN,
        "custom_check": CompletionType.CUSTOM_CHECK,
    }

    c_type = type_map.get(completion_type, CompletionType.MARKER_FILE)
    criteria = completion_criteria or {}

    task_path = Path(task_file)
    if not task_path.is_absolute():
        task_path = get_seed_dir_with_fallback() / "tasks" / task_file

    return RalphLoop(
        agent_loop=agent_loop,
        completion_type=c_type,
        completion_criteria=criteria,
        task_prompt_path=task_path,
        **kwargs,
    )


__all__ = [
    "RalphLoop",
    "CompletionType",
    "create_ralph_loop",
]