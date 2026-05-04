"""自主探索模块：空闲时根据 SOP 执行自主任务

增强版 (Ralph Loop + Memory Graph 集成):
- completion_promise 检测：外部完成标志驱动退出
- 可选上下文重置：防止上下文漂移
- 防无限循环上限：迭代和时间双重保护
- Memory Graph 选择：基于历史结果选择最佳 Skill
- 自动结果记录：执行完成后自动记录 outcome
- Session 事件记录：所有状态变更通过 Session 正确记录
"""

import asyncio
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

import contextlib

from src.ralph_state import (
    SEED_DIR,
    RalphState,
    check_safety_limits,
    cleanup_state_file,
    extract_critical_context,
    load_or_init_state,
    persist_state,
)
from src.session_event_stream import EventType

logger = logging.getLogger("seed_agent")

# 项目根目录（当前文件所在目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
# SOP 文档路径
SOP_PATH = PROJECT_ROOT / "auto" / "自主探索 SOP.md"

# Ralph Loop 增强配置
COMPLETION_PROMISE_FILE = SEED_DIR / "completion_promise"
COMPLETION_PROMISE_TOKENS = ["DONE", "COMPLETE", "TASK_FINISHED"]
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5  # 每5轮迭代重置
RALPH_MAX_ITERATIONS = 1000  # 理论上限
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间

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


class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强)

    新增特性:
    - completion_promise 检测：外部标志驱动退出
    - 可选上下文重置：防止上下文漂移
    - 防无限循环上限：迭代和时间双重保护
    - Session 事件记录：所有状态变更通过 Session 正确记录
    - 状态文件固定：进程重启后可恢复状态

    修复:
    - 不直接修改 AgentLoop.history（这是兼容性接口，赋值无效）
    - 使用 Session API 记录自主探索开始/结束事件
    - 状态文件名固定，避免碎片化
    - 完成检测添加原子操作保护
    """

    # 固定状态文件名，进程重启后可恢复
    STATE_FILE_NAME = "autonomous_state.json"

    # 原子操作锁（用于完成检测）
    _completion_check_lock = threading.Lock()

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable[[str], None]
        | Callable[[str], Coroutine[Any, Any, None]]
        | None = None,
    ):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete
        self._last_activity: float = time.time()
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._sop_content: str | None = None
        self._iteration_count: int = 0  # Ralph Loop 迭代计数
        self._ralph_start_time: float = 0.0  # 当前会话开始时间
        self._accumulated_duration: float = 0.0  # 累计执行时间（跨会话）
        self._empty_response_count: int = 0  # 空响应计数
        # TODO 内容缓存（TTL 30秒）
        self._todo_cache: str | None = None
        self._todo_cache_time: float = 0.0
        self._todo_cache_ttl: float = 30.0  # 缓存有效期（秒）
        # 使用固定状态文件名，进程重启后可恢复
        self._state_file: Path = SEED_DIR / "ralph" / self.STATE_FILE_NAME
        # 从配置读取 IDLE_TIMEOUT
        from src.shared_config import get_autonomous_config

        self._idle_timeout: float = get_autonomous_config().idle_timeout_hours * 60 * 60
        self._load_sop()

    def _load_sop(self) -> None:
        """加载自主探索 SOP"""
        if SOP_PATH.exists():
            try:
                with open(SOP_PATH, encoding="utf-8") as f:
                    self._sop_content = f.read()
                logger.info(f"Loaded autonomous SOP from {SOP_PATH}")
            except OSError as e:
                logger.warning(f"Failed to read SOP file {SOP_PATH}: {e}")
                self._sop_content = ""
        else:
            logger.warning(f"SOP file not found: {SOP_PATH}")

    def record_activity(self):
        """记录用户活动时间"""
        self._last_activity = time.time()

    def get_idle_time(self) -> float:
        """获取当前空闲时间（秒）"""
        return time.time() - self._last_activity

    async def start(self):
        """启动空闲监控"""
        if self._running:
            return

        # 检查 SOP 文件是否存在
        if not self._sop_content:
            logger.warning(
                f"SOP file not found: {SOP_PATH} - autonomous exploration disabled"
            )
            return

        self._running = True
        self._task = asyncio.create_task(self._idle_monitor_loop())
        logger.warning("Autonomous explorer started")

    async def stop(self):
        """停止空闲监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.warning("Autonomous explorer stopped")

    async def _idle_monitor_loop(self):
        """空闲监控循环"""
        while self._running:
            idle_time = self.get_idle_time()

            if idle_time >= self._idle_timeout:
                logger.warning(
                    f"Idle for {idle_time / 60:.1f} minutes, starting autonomous exploration"
                )
                result = await self._execute_autonomous_task()
                if result:
                    self.record_activity()  # 仅成功时重置计时
                else:
                    logger.warning(
                        "Autonomous exploration failed, not resetting idle timer"
                    )

            # 每30秒检查一次
            await asyncio.sleep(30)

    # === Ralph Loop 增强方法 ===

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志（Ralph Loop 核心机制，原子化版本）

        使用锁保护文件检查与删除操作，防止多进程/多线程竞态条件。
        """
        with self._completion_check_lock:
            if COMPLETION_PROMISE_FILE.exists():
                try:
                    content = COMPLETION_PROMISE_FILE.read_text().strip()
                    if content in COMPLETION_PROMISE_TOKENS:
                        logger.info(f"Completion promise detected: {content}")
                        # 清除标志
                        COMPLETION_PROMISE_FILE.unlink()
                        return True
                except OSError as e:
                    logger.warning(f"Failed to read/delete completion promise: {e}")
        return False

    def _check_safety_limits(self) -> bool:
        """检查安全上限（防止无限循环，使用共享模块）"""
        return check_safety_limits(
            iteration=self._iteration_count,
            max_iterations=RALPH_MAX_ITERATIONS,
            start_time=self._ralph_start_time,
            accumulated_duration=self._accumulated_duration,
            max_duration=RALPH_MAX_DURATION,
        )

    def _extract_critical_context(self) -> str | None:
        """提取关键上下文（包装共享模块函数，保持向后兼容）"""
        return extract_critical_context(self.agent.history)

    async def _reset_context_if_needed(self) -> str | None:
        """条件性重置上下文（防止上下文漂移）

        使用 SessionEventStream 的上下文重置标记，而不是直接清空 history。
        这样确保所有状态变更都通过 Session 正确记录。

        关键修复：确保自主探索的 prompt（system_prompt）在重置后仍然保留，
        否则 LLM 会误判为"收到空消息"。
        """
        if not CONTEXT_RESET_ENABLED:
            return None

        # 仅在指定间隔执行
        if self._iteration_count % CONTEXT_RESET_INTERVAL != 0:
            return None

        # 提取关键上下文（从 history）
        history_context = extract_critical_context(self.agent.history) or ""

        # 关键修复：保留自主探索的核心指令（从 system_prompt 提取关键部分）
        # 避免在上下文重置后丢失自主探索的任务指引
        autonomous_prompt = self.agent.system_prompt or ""
        # 提取 SOP 和任务指令部分（而非完整 skills prompt）
        preserved_autonomous = self._extract_autonomous_prompt_core(autonomous_prompt)

        # 合并：自主探索指令 + 上次执行摘要
        preserved = (
            f"{preserved_autonomous}\n\n---\n\n{history_context}"
            if history_context
            else preserved_autonomous
        )

        # 通过 Session 创建上下文重置标记
        self.agent.session.create_context_reset_marker(
            iteration=self._iteration_count, preserved_context=preserved
        )

        logger.info(
            f"Context reset marker created at iteration {self._iteration_count}"
        )
        return preserved

    def _extract_autonomous_prompt_core(self, full_prompt: str) -> str:
        """从完整自主探索 prompt 中提取核心指令部分（增强版）

        只保留 SOP 和任务指令，避免重复注入 skills（会导致上下文膨胀）。

        增强点：
        1. 如果提取失败，使用已加载的 SOP 作为 fallback
        2. 如果任务指令缺失，动态构建当前任务
        3. 确保始终返回有效内容（非空）
        """
        # 匹配 SOP 部分
        sop_match = re.search(
            r"(##?\s*自主探索\s*SOP.*?)(?=##?\s*|$)",
            full_prompt,
            re.DOTALL | re.IGNORECASE,
        )
        sop_content = sop_match.group(1) if sop_match else ""

        # 如果提取失败，使用已加载的 SOP
        if not sop_content and self._sop_content:
            sop_content = f"## 自主探索 SOP\n\n{self._sop_content}"

        # 匹配任务指令部分
        task_match = re.search(
            r"(##?\s*自主探索任务触发.*?)(?=请开始执行|$)",
            full_prompt,
            re.DOTALL | re.IGNORECASE,
        )
        task_content = task_match.group(1) if task_match else ""

        # 如果任务指令缺失，动态构建当前任务
        if not task_content:
            todo_content = self._load_todo_content()
            has_todo = bool(todo_content)
            task_content = self._build_task_instruction(todo_content, has_todo)

        # 合并核心部分
        core_parts = []
        if sop_content:
            core_parts.append(sop_content.strip())
        if task_content:
            core_parts.append(task_content.strip())

        # 确保返回有效内容
        if core_parts:
            return "\n\n".join(core_parts)

        # 使用已加载的 SOP 作为 fallback
        if self._sop_content:
            return f"## 自主探索 SOP\n\n{self._sop_content}"

        # 最终 fallback：返回 prompt 的前 3000 字符
        return full_prompt[:3000] if full_prompt else "继续执行自主探索任务"

    def _persist_state(self, response: str = ""):
        """持久化当前状态（使用共享模块）"""
        persist_state(
            state_file=self._state_file,
            iteration=self._iteration_count,
            start_time=self._ralph_start_time,
            accumulated_duration=self._accumulated_duration,
            response=response,
        )

    def _load_or_init_state(self):
        """加载或初始化状态（使用共享模块）

        如果加载的状态已达到迭代上限，则重置状态开始新会话。
        """
        state = load_or_init_state(self._state_file)

        # 如果迭代次数已达到上限，重置状态开始新会话
        if state.iteration >= RALPH_MAX_ITERATIONS:
            logger.warning(
                f"Loaded state has reached max iterations ({state.iteration}/{RALPH_MAX_ITERATIONS}), "
                "resetting for new session"
            )
            self._cleanup_state()  # 清理旧状态文件
            state = RalphState()  # 重新初始化

        self._iteration_count = state.iteration
        self._accumulated_duration = state.accumulated_duration
        self._ralph_start_time = state.start_time
        self._empty_response_count = 0  # 重置空响应计数

    def _cleanup_state(self):
        """清理状态文件（使用共享模块）"""
        cleanup_state_file(self._state_file)

    async def _execute_autonomous_task(self):
        """执行自主探索任务（复用 Agent Loop + Ralph Loop 增强）

        关键修复：
        1. 不保存/恢复 history（history 是兼容性接口，赋值无效）
        2. 使用 Session 标记自主探索开始/结束
        3. 通过 Session 创建上下文边界
        4. **启用 autonomous_mode 防止 Ask User 阻塞**

        这样确保：
        - Session 包含自主探索的完整事件历史
        - 用户交互时上下文可正确区分自主探索事件
        - Ask User 被自动跳过，不会阻塞等待用户响应
        """
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return None

        self._load_or_init_state()
        todo_content = self._load_todo_content()
        prompt = self._build_autonomous_prompt(todo_content, bool(todo_content))

        # 创建自主探索开始标记
        self.agent.session.emit_event(
            EventType.SESSION_START,
            {
                "type": "autonomous_exploration",
                "iteration": self._iteration_count,
                "todo_status": bool(todo_content),
            },
        )

        logger.info("Starting autonomous exploration via Agent Loop (Ralph enhanced)")

        # 只保存/恢复 system_prompt 和 max_iterations
        # 不再操作 history（history 是兼容性接口，赋值无效）
        original_system_prompt = self.agent.system_prompt
        original_max_iterations = self.agent.max_iterations

        # === 新增：启用 autonomous_mode ===
        # 从配置读取 Ask User 跳过响应
        from src.shared_config import get_autonomous_config

        autonomous_config = get_autonomous_config()
        self.agent.set_autonomous_mode(
            enabled=True,
            skip_response=autonomous_config.ask_user_skip_response,
        )

        try:
            self.agent.system_prompt = prompt
            self.agent.max_iterations = 100
            response = await self._run_ralph_loop()

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
                    },
                )

                if self.on_explore_complete:
                    if asyncio.iscoroutinefunction(self.on_explore_complete):
                        await self.on_explore_complete(response)
                    else:
                        self.on_explore_complete(response)
                return response
            logger.warning("Autonomous exploration returned empty response")

            # 创建失败标记
            self.agent.session.emit_event(
                EventType.SESSION_END,
                {"type": "autonomous_exploration", "reason": "empty_response"},
            )
            return None

        except Exception as e:
            logger.exception(f"Autonomous exploration failed: {e}")
            self._persist_state(str(e))

            # 创建错误标记
            self.agent.session.emit_event(
                EventType.ERROR_OCCURRED,
                {
                    "error_type": "autonomous_exploration_failed",
                    "error_message": str(e)[:500],
                },
            )
            return None

        finally:
            # === 新增：恢复正常模式 ===
            self.agent.set_autonomous_mode(enabled=False)
            self.agent.system_prompt = original_system_prompt
            self.agent.max_iterations = original_max_iterations
            # 不再恢复 history（无效操作）

    def _load_todo_content(self) -> str:
        """加载TODO文件内容（带 TTL 缓存）

        缓存策略：30秒内不重复读取文件，减少 I/O 开销
        """
        now = time.time()
        # 缓存有效，直接返回
        if (
            self._todo_cache is not None
            and now - self._todo_cache_time < self._todo_cache_ttl
        ):
            return self._todo_cache

        todo_path = SEED_DIR / "TODO.md"
        if todo_path.exists():
            try:
                with open(todo_path, encoding="utf-8") as f:
                    content = f.read()
                # 更新缓存
                self._todo_cache = content
                self._todo_cache_time = now
                return content
            except OSError as e:
                logger.warning(f"Failed to read TODO file {todo_path}: {e}")
        # 缓存空内容
        self._todo_cache = ""
        self._todo_cache_time = now
        return ""

    async def _run_ralph_loop(self) -> str | None:
        """执行 Ralph Loop 主循环（增强版）

        增强特性：
        - 超时保护：LLM 单次调用有超时限制
        - 异常处理扩展：捕获所有异常类型，记录后继续
        - 详细调试日志：记录 LLM 调用前/后状态、工具执行
        - 错误恢复退避：连续失败后等待再重试

        Returns:
            最终响应文本，或 None 表示失败
        """
        from src.shared_config import get_autonomous_config

        autonomous_config = get_autonomous_config()
        llm_timeout = autonomous_config.llm_call_timeout_seconds
        failure_threshold = autonomous_config.consecutive_failure_threshold
        backoff_duration = autonomous_config.backoff_duration_seconds
        max_backoff = autonomous_config.max_backoff_multiplier * backoff_duration
        debug_enabled = autonomous_config.debug_logging_enabled

        response: str | None = None
        next_prompt: str = "继续执行自主探索任务"
        consecutive_failures: int = 0

        while True:
            self._iteration_count += 1

            # === 安全上限检查 ===
            if self._check_safety_limits():
                logger.info(
                    "Ralph Loop safety limit reached, cleaning up state for next session"
                )
                self._cleanup_state()
                break

            # === 完成标志检查 ===
            if self._check_completion_promise():
                logger.info("Completion promise detected, exiting Ralph loop")
                self._cleanup_state()
                await self._notify_completion("DONE")
                return "DONE"

            # === 上下文重置 ===
            await self._reset_context_if_needed()

            # === 调试日志：LLM 调用前 ===
            if debug_enabled:
                logger.debug(
                    f"[Ralph Loop] Iteration {self._iteration_count}: "
                    f"prompt='{next_prompt[:100]}...', "
                    f"failures={consecutive_failures}/{failure_threshold}"
                )

            # === LLM 调用（带超时保护）===
            try:
                response = await asyncio.wait_for(
                    self.agent.run(next_prompt, wait_for_user=False),
                    timeout=llm_timeout,
                )

                # === 调试日志：LLM 调用成功 ===
                if debug_enabled:
                    logger.debug(
                        f"[Ralph Loop] Iteration {self._iteration_count}: "
                        f"response='{response[:200] if response else 'None'}...', "
                        f"length={len(response) if response else 0}"
                    )

                # 成功时重置失败计数
                consecutive_failures = 0

            except TimeoutError:
                # === 超时处理 ===
                logger.warning(
                    f"[Ralph Loop] Iteration {self._iteration_count}: "
                    f"LLM call timeout ({llm_timeout}s), skipping iteration"
                )
                consecutive_failures += 1
                response = f"[TIMEOUT] LLM call exceeded {llm_timeout}s limit"

            except (
                RuntimeError,
                OSError,
                ValueError,
                asyncio.CancelledError,
                KeyError,
            ) as e:
                # === 异常处理（扩展版）===
                logger.warning(
                    f"[Ralph Loop] Iteration {self._iteration_count}: "
                    f"Agent execution error: {type(e).__name__}: {e!s}"
                )
                consecutive_failures += 1
                response = f"Error: {type(e).__name__}: {e!s}"

            except Exception as e:
                # === 捕获所有未预期异常 ===
                logger.exception(
                    f"[Ralph Loop] Iteration {self._iteration_count}: "
                    f"Unexpected error: {type(e).__name__}"
                )
                consecutive_failures += 1
                response = f"Unexpected Error: {type(e).__name__}: {e!s}"

            # === 状态持久化 ===
            self._persist_state(response or "")

            # === 错误恢复退避 ===
            if consecutive_failures >= failure_threshold:
                # 计算退避时间（指数增长，上限 max_backoff）
                backoff = min(
                    backoff_duration
                    * (2 ** (consecutive_failures - failure_threshold)),
                    max_backoff,
                )
                logger.warning(
                    f"[Ralph Loop] Consecutive failures {consecutive_failures}, "
                    f"backing off for {backoff}s"
                )
                await asyncio.sleep(backoff)
                # 重置计数（退避后）
                if consecutive_failures >= failure_threshold * 2:
                    consecutive_failures = 0

            # === 完成检测 ===
            if response and any(marker in response for marker in COMPLETION_MARKERS):
                logger.info(
                    f"Autonomous exploration completed at iteration {self._iteration_count}"
                )
                self._cleanup_state()
                break

            # === 下一轮 prompt ===
            next_prompt = (
                await self._handle_response(response) or "继续执行自主探索任务"
            )
            await asyncio.sleep(2)

        return response

    async def _notify_completion(self, result: str):
        """通知探索完成"""
        if self.on_explore_complete:
            if asyncio.iscoroutinefunction(self.on_explore_complete):
                await self.on_explore_complete(result)
            else:
                self.on_explore_complete(result)

    async def _handle_response(self, response: str | None) -> str | None:
        """处理agent响应并返回下一轮的 prompt

        不再直接修改 history，而是返回合适的 prompt 供下一轮 run() 使用。
        这样所有用户输入都通过 SessionEventStream 正确记录。

        Returns:
            下一轮执行的 prompt，或者 None 表示不继续
        """
        if not response:
            self._empty_response_count += 1
            logger.warning(
                f"Empty response at iteration {self._iteration_count} "
                f"(count: {self._empty_response_count})"
            )
            if self._empty_response_count >= 3:
                logger.warning("Too many empty responses, trying simplified prompt")
                return "请报告当前状态"
            # 返回简化的继续提示，而不是完整的 SOP
            return "继续执行自主探索任务，请报告进展"
        return None

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt（包含完整 system prompt + skills + SOP + Memory Graph 选择）"""
        # 获取 agent 的 system prompt（已包含 skills）
        base_system_prompt = self.agent.system_prompt or ""

        # 获取 skills prompt（从 skill_loader）
        skills_prompt = ""
        best_skill_suggestion = ""
        skill_loader = getattr(self.agent, "skill_loader", None)
        if skill_loader:
            skills_prompt = skill_loader.get_skills_prompt()

            # Memory Graph 增强：根据任务类型选择最佳 skill
            signals = self._extract_task_signals(todo_content, has_todo)
            best_skill = skill_loader.select_best_skill(
                signals=signals,
                available_tools=getattr(
                    self.agent.tools, "get_tool_names", lambda: None
                )(),
            )

            if best_skill:
                # 使用 Gene slice（Tier 2a）注入，而非完整 skill
                gene_slice = skill_loader.get_gene_slice(best_skill)
                if gene_slice:
                    best_skill_suggestion = f"""## 推荐技能 (Memory Graph 选择)

基于历史成功率，推荐使用技能: **{best_skill}**

{gene_slice}

"""
                    logger.info(f"Memory Graph selected skill: {best_skill}")

        # 构建 SOP 内容（替换 ~ 路径为实际路径）
        # 将 SOP 中的 ~/.seed 替换为实际的 SEED_DIR 绝对路径
        sop_content_expanded = self._sop_content or ""
        if sop_content_expanded:
            seed_dir_str = str(SEED_DIR)
            # 替换所有 ~/.seed 相关路径
            sop_content_expanded = sop_content_expanded.replace("~/.seed", seed_dir_str)
            sop_content_expanded = sop_content_expanded.replace("~\\seed", seed_dir_str)
            # 替换 ~ 为用户主目录
            home_dir = os.path.expanduser("~")
            sop_content_expanded = sop_content_expanded.replace("~", home_dir)

        sop_prompt = f"""## 自主探索 SOP

{sop_content_expanded}

"""

        # 构建任务指令
        task_prompt = self._build_task_instruction(todo_content, has_todo)

        # 组合完整 prompt
        parts = []
        if base_system_prompt:
            parts.append(base_system_prompt)
        if skills_prompt and skills_prompt not in base_system_prompt:
            parts.append(skills_prompt)
        if best_skill_suggestion:
            parts.append(best_skill_suggestion)
        parts.append(sop_prompt)
        parts.append(task_prompt)

        return "\n\n".join(parts)

    def _extract_task_signals(self, todo_content: str, has_todo: bool) -> list[str]:
        """从任务内容提取触发信号"""
        signals = []

        if has_todo and todo_content:
            # 从 TODO 内容提取关键词
            lines = todo_content.split("\n")
            for line in lines[:5]:
                # 提取 TODO 条目中的关键词
                if line.strip():
                    words = line.split()
                    signals.extend(words[:3])

        # 根据任务类型添加基础信号
        if has_todo:
            signals.append("execute")
            signals.append("task")
        else:
            signals.append("plan")
            signals.append("generate")

        return signals[:10]

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令部分"""
        # 获取 SEED_DIR 的绝对路径（用于明确告知 LLM）
        seed_dir_absolute = str(SEED_DIR)
        # 获取项目目录（PROJECT_ROOT）的绝对路径
        project_root_absolute = str(PROJECT_ROOT)

        prompt_parts = [
            "# 自主探索任务触发",
            "",
            "当前空闲2小时，开始执行自主任务。",
            "",
            "## 当前状态",
            f"- TODO状态: {'有待执行任务' if has_todo else '无TODO，进入规划模式'}",
            f"- 工作目录: {seed_dir_absolute}",
            "",
            "## 重要路径说明（使用绝对路径）",
            "",
            "### 记忆系统路径（位于用户目录）",
            f"- 记忆目录: {os.path.join(seed_dir_absolute, 'memory')}",
            f"- Skills目录: {os.path.join(seed_dir_absolute, 'memory', 'skills')}",
            f"- TODO文件: {os.path.join(seed_dir_absolute, 'TODO.md')}",
            f"- 日志目录: {os.path.join(seed_dir_absolute, 'logs')}",
            "",
            "### 项目源码路径（位于项目目录）",
            f"- 项目根目录: {project_root_absolute}",
            f"- 源码目录: {os.path.join(project_root_absolute, 'src')}",
            f"- Agent模块: {os.path.join(project_root_absolute, 'src', 'agent_loop.py')}",
            f"- LLM Gateway: {os.path.join(project_root_absolute, 'src', 'client.py')}",
            f"- 工具模块: {os.path.join(project_root_absolute, 'src', 'tools')}",
            "",
            "**关键提示**: ",
            "1. 记忆系统文件（Skills、TODO等）使用 `.seed` 目录下的绝对路径",
            "2. 项目源码文件（src/*.py）使用项目目录下的绝对路径",
            "3. 不要混淆两者：`src/client.py` 应为 `{os.path.join(project_root_absolute, 'src', 'client.py')}`，而非 `{os.path.join(seed_dir_absolute, 'src', 'client.py')}`",
            "",
        ]

        if has_todo and todo_content.strip():
            prompt_parts.extend(
                [
                    "## 当前TODO内容",
                    todo_content,
                    "",
                    "请按照 SOP 执行流程，逐个完成 TODO 条目：",
                    "1. 在 <thinking> 内推演执行逻辑",
                    "2. 执行任务并记录到工作记忆",
                    "3. 完成后标记 TODO 并更新工作记忆",
                    "",
                ]
            )
        else:
            prompt_parts.extend(
                [
                    "## 规划模式",
                    "当前无TODO，请进入规划模式：",
                    "1. 读取 history.md 和工作记忆",
                    "2. 反思低价值操作，提炼进化线索",
                    "3. 产出5-7条TODO（格式：`[ ] 类型 | 目标 | 验收标准 | 预期沉淀`）",
                    "4. 更新 TODO.md 文件",
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "## SOP 核心原则",
                "- 价值公式：实际执行可落地性 × 进化沉淀价值",
                "- 不推诿、有逻辑、重沉淀",
                "- 失败升级：1次重试，2次探测，3次换方案",
                "- 不可逆操作需先确认用户（但自主模式下跳过需确认的操作）",
                "",
                "请开始执行自主探索任务。",
            ]
        )

        return "\n".join(prompt_parts)


async def create_autonomous_explorer(
    agent_loop, on_explore_complete: Callable | None = None
) -> AutonomousExplorer:
    """创建自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer
