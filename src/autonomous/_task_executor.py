"""任务执行模块

提供自主探索任务执行功能:
- execute_autonomous_task: 执行自主探索任务
- run_ralph_loop: Ralph Loop 主循环
- handle_response: 处理响应
- notify_completion: 通知探索完成

从 AutonomousExplorer 中提取，保持接口不变。
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import check_safety_limits, extract_critical_context
from src.session_event_stream import EventType
from src.shared_config import get_autonomous_config, get_seed_dir_with_fallback

from ._defense import DefenseState, check_completion_promise
from ._prompt_builder import (
    build_autonomous_prompt,
    build_task_instruction,
    extract_autonomous_prompt_core,
    extract_task_signals,
)
from ._sop_loader import expand_sop_paths, load_sop
from ._state_manager import StateManager, TodoCache

logger = logging.getLogger("seed_agent")

# Ralph Loop 增强配置
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5  # 每5轮迭代重置
RALPH_MAX_ITERATIONS = 1000  # 理论上限（安全兜底）
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间（安全兜底）

# 任务完成检测标记（支持多语言）
COMPLETION_MARKERS = [
    "任务完成",
    "已完成",
    "DONE",
    "COMPLETE",
    "FINISHED",
    "done",
    "complete",
    "finished",
]


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
        return check_safety_limits(
            iteration=self._state_manager.get_iteration_count(),
            max_iterations=RALPH_MAX_ITERATIONS,
            start_time=self._state_manager.get_start_time(),
            accumulated_duration=self._state_manager.get_accumulated_duration(),
            max_duration=RALPH_MAX_DURATION,
        )

    async def execute_autonomous_task(self) -> str | None:
        """执行自主探索任务（复用 Agent Loop + Ralph Loop 增强 + 四层防御）

        Returns:
            str | None: 探索结果文本，失败时返回 None
        """
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return None

        self._state_manager.load_or_init_state()

        # === Layer 4: 获取重试预算 ===
        max_iterations = self._defense.get_retry_budget()
        if max_iterations == 0:
            logger.warning(
                f"Retry count {self._defense.get_retry_count()} exceeds max "
                f"{self._config.max_retry_count}, stopping autonomous exploration"
            )
            return None

        # === 重置四层防御状态 ===
        self._defense.reset()

        todo_content = self._todo_cache.load_todo_content(self._seed_dir)
        expanded_sop = expand_sop_paths(self._sop_content, self._seed_dir)

        # 构建 prompt
        prompt = self._build_full_prompt(todo_content)

        # 创建自主探索开始标记
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
            f"Starting autonomous exploration (Ralph enhanced + 4-layer defense): "
            f"budget={max_iterations}, retry={self._defense.get_retry_count()}"
        )

        # 保存/恢复 system_prompt 和 max_iterations
        original_system_prompt = self.agent.system_prompt
        original_max_iterations = self.agent.max_iterations

        # === 启用 autonomous_mode ===
        self.agent.set_autonomous_mode(
            enabled=True,
            skip_response=self._config.ask_user_skip_response,
        )

        try:
            self.agent.system_prompt = prompt
            self.agent.max_iterations = max_iterations

            # 传入预算参数用于四层防御检查
            response = await self._run_ralph_loop(max_iterations)

            if response:
                logger.info(
                    f"Autonomous exploration completed, response length: {len(response)}"
                )

                # 创建自主探索结束标记
                self.agent.session.emit_event(
                    EventType.SESSION_END,
                    {
                        "type": "autonomous_exploration",
                        "reason": "completed",
                        "response_length": len(response),
                        "iterations_used": self._state_manager.get_iteration_count(),
                    },
                )

                # 成功完成，重置重试计数
                self._defense.reset_retry()

                await self._notify_completion(response)
                return response

            # === 失败处理：增加重试计数 ===
            self._defense.increment_retry()
            logger.warning(
                f"Autonomous exploration returned empty response, "
                f"retry_count now {self._defense.get_retry_count()}"
            )

            # 创建失败标记
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

            # === 异常处理：增加重试计数 ===
            self._defense.increment_retry()

            # 创建错误标记
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
            # === 恢复正常模式 ===
            self.agent.set_autonomous_mode(enabled=False)
            self.agent.system_prompt = original_system_prompt
            self.agent.max_iterations = original_max_iterations

    def _build_full_prompt(self, todo_content: str) -> str:
        """构建完整的自主探索 prompt

        Args:
            todo_content: TODO 文件内容

        Returns:
            完整 prompt
        """
        base_system_prompt = self.agent.system_prompt or ""

        # 获取 skills prompt
        skills_prompt = ""
        best_skill = None
        gene_slice = None

        skill_loader = getattr(self.agent, "skill_loader", None)
        if skill_loader:
            skills_prompt = skill_loader.get_skills_prompt()

            # Memory Graph 增强：根据任务类型选择最佳 skill
            signals = extract_task_signals(todo_content, bool(todo_content))
            best_skill = skill_loader.select_best_skill(
                signals=signals,
                available_tools=getattr(
                    self.agent.tools, "get_tool_names", lambda: None
                )(),
            )

            if best_skill:
                gene_slice = skill_loader.get_gene_slice(best_skill)

        # 展开 SOP 路径
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

    async def _run_ralph_loop(self, max_budget: int | None = None) -> str | None:
        """执行 Ralph Loop 主循环（增强版 + 四层防御）

        Args:
            max_budget: 迭代预算上限

        Returns:
            最终响应文本，或 None 表示失败
        """
        llm_timeout = self._config.llm_call_timeout_seconds
        failure_threshold = self._config.consecutive_failure_threshold
        backoff_duration = self._config.backoff_duration_seconds
        max_backoff = self._config.max_backoff_multiplier * backoff_duration
        debug_enabled = self._config.debug_logging_enabled

        # 使用传入预算或配置默认值
        budget = max_budget or self._config.max_iterations_per_task

        response: str | None = None
        next_prompt: str = "继续执行自主探索任务"
        consecutive_failures: int = 0

        while True:
            iteration = self._state_manager.increment_iteration()

            # === 多层防御检查 ===

            # Layer 1: 预算警告注入
            await self._defense.inject_budget_warning(iteration, budget, self.agent)

            # Layer 2: 进度检测窗口
            if not self._defense.check_progress_window():
                logger.info("进度检测判定空转，提前终止")
                break

            # Layer 3: 时间断路器
            if not self._defense.check_time_circuit_breaker(self.agent):
                logger.info("时间断路器触发，强制终止")
                break

            # 安全上限检查
            if self._check_safety_limits():
                logger.info(
                    "Ralph Loop safety limit reached, cleaning up state for next session"
                )
                self._state_manager.cleanup_state()
                break

            # 预算上限检查
            if iteration >= budget:
                logger.info(f"迭代预算耗尽 ({iteration}/{budget}), 结束循环")
                break

            # === 完成标志检查 ===
            if self._check_completion_promise():
                logger.info("Completion promise detected, exiting Ralph loop")
                self._state_manager.cleanup_state()
                await self._notify_completion("DONE")
                return "DONE"

            # === 上下文重置 ===
            await self._reset_context_if_needed()

            # === 调试日志 ===
            if debug_enabled:
                logger.debug(
                    f"[Ralph Loop] Iteration {iteration}: "
                    f"prompt='{next_prompt[:100]}...', "
                    f"failures={consecutive_failures}/{failure_threshold}, "
                    f"time_elapsed={self._defense.get_task_elapsed_time():.0f}s"
                )

            # === LLM 调用（带超时保护）===
            try:
                response = await asyncio.wait_for(
                    self.agent.run(next_prompt, wait_for_user=False),
                    timeout=llm_timeout,
                )

                # 记录工具调用历史
                self._record_tool_calls()

                if debug_enabled:
                    logger.debug(
                        f"[Ralph Loop] Iteration {iteration}: "
                        f"response='{response[:200] if response else 'None'}...', "
                        f"length={len(response) if response else 0}"
                    )

                consecutive_failures = 0

            except TimeoutError:
                logger.warning(
                    f"[Ralph Loop] Iteration {iteration}: "
                    f"LLM call timeout ({llm_timeout}s), skipping iteration"
                )
                consecutive_failures += 1
                response = f"[TIMEOUT] LLM call exceeded {llm_timeout}s limit"

            except (RuntimeError, OSError, ValueError, asyncio.CancelledError, KeyError) as e:
                logger.warning(
                    f"[Ralph Loop] Iteration {iteration}: "
                    f"Agent execution error: {type(e).__name__}: {e!s}"
                )
                consecutive_failures += 1
                response = f"Error: {type(e).__name__}: {e!s}"

            except Exception as e:
                logger.exception(
                    f"[Ralph Loop] Iteration {iteration}: "
                    f"Unexpected error: {type(e).__name__}"
                )
                consecutive_failures += 1
                response = f"Unexpected Error: {type(e).__name__}: {e!s}"

            # === 状态持久化 ===
            self._state_manager.persist_state(response or "")

            # === 错误恢复退避 ===
            if consecutive_failures >= failure_threshold:
                backoff = min(
                    backoff_duration * (2 ** (consecutive_failures - failure_threshold)),
                    max_backoff,
                )
                logger.warning(
                    f"[Ralph Loop] Consecutive failures {consecutive_failures}, "
                    f"backing off for {backoff}s"
                )
                await asyncio.sleep(backoff)
                if consecutive_failures >= failure_threshold * 2:
                    consecutive_failures = 0

            # === 完成检测 ===
            if response and any(marker in response for marker in COMPLETION_MARKERS):
                logger.info(f"Autonomous exploration completed at iteration {iteration}")
                self._state_manager.cleanup_state()
                break

            # === 下一轮 prompt ===
            next_prompt = await self._handle_response(response) or "继续执行自主探索任务"
            await asyncio.sleep(2)

        return response

    def _record_tool_calls(self) -> None:
        """记录工具调用历史（从 Session 获取最近的工具调用）"""
        iteration = self._state_manager.get_iteration_count()
        recent_events = self.agent.session.get_events(start_id=-5)
        for event in recent_events:
            if event["type"] == EventType.TOOL_CALL.value:
                tool_data = event.get("data", {})
                self._defense.add_action(tool_data.get("tool_name", ""), iteration)

    async def _reset_context_if_needed(self) -> str | None:
        """条件性重置上下文（防止上下文漂移）"""
        if not CONTEXT_RESET_ENABLED:
            return None

        iteration = self._state_manager.get_iteration_count()
        if iteration % CONTEXT_RESET_INTERVAL != 0:
            return None

        # 提取关键上下文
        history_context = extract_critical_context(self.agent.history) or ""

        # 保留自主探索的核心指令
        autonomous_prompt = self.agent.system_prompt or ""
        preserved_autonomous = extract_autonomous_prompt_core(
            autonomous_prompt, self._sop_content
        )

        # 合并
        preserved = (
            f"{preserved_autonomous}\n\n---\n\n{history_context}"
            if history_context
            else preserved_autonomous
        )

        # 通过 Session 创建上下文重置标记
        self.agent.session.create_context_reset_marker(
            iteration=iteration, preserved_context=preserved
        )

        logger.info(f"Context reset marker created at iteration {iteration}")
        return preserved

    async def _handle_response(self, response: str | None) -> str | None:
        """处理响应并返回下一轮的 prompt

        Args:
            response: 当前响应

        Returns:
            下一轮执行的 prompt，或 None 表示不继续
        """
        if not response:
            self._state_manager.increment_empty_response()
            logger.warning(
                f"Empty response at iteration {self._state_manager.get_iteration_count()} "
                f"(count: {self._state_manager.get_empty_response_count()})"
            )
            if self._state_manager.get_empty_response_count() >= 3:
                logger.warning("Too many empty responses, trying simplified prompt")
                return "请报告当前状态"
            return "继续执行自主探索任务，请报告进展"
        return None

    async def _notify_completion(self, result: str) -> None:
        """通知探索完成"""
        if self.on_explore_complete:
            if asyncio.iscoroutinefunction(self.on_explore_complete):
                await self.on_explore_complete(result)
            else:
                self.on_explore_complete(result)