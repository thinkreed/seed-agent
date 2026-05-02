"""自主探索模块：空闲时根据 SOP 执行自主任务

增强版 (Ralph Loop + Memory Graph 集成):
- completion_promise 检测：外部完成标志驱动退出
- 可选上下文重置：防止上下文漂移
- 防无限循环上限：迭代和时间双重保护
- Memory Graph 选择：基于历史结果选择最佳 Skill
- 自动结果记录：执行完成后自动记录 outcome
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import (
    RalphState,
    SEED_DIR,
    check_safety_limits,
    cleanup_state_file,
    extract_critical_context,
    load_or_init_state,
    persist_state,
    reset_context,
)

logger = logging.getLogger("seed_agent")

# 项目根目录（当前文件所在目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
# SOP 文档路径
SOP_PATH = PROJECT_ROOT / "auto" / "自主探索 SOP.md"

# Ralph Loop 增强配置
COMPLETION_PROMISE_FILE = SEED_DIR / "completion_promise"
COMPLETION_PROMISE_TOKENS = ["DONE", "COMPLETE", "TASK_FINISHED"]
CONTEXT_RESET_ENABLED = True  # 默认开启
CONTEXT_RESET_INTERVAL = 5    # 每5轮迭代重置
RALPH_MAX_ITERATIONS = 1000   # 理论上限
RALPH_MAX_DURATION = 8 * 60 * 60  # 8小时最大执行时间

# 任务完成检测标记（支持多语言）
COMPLETION_MARKERS = ["任务完成", "已完成", "DONE", "COMPLETE", "FINISHED", "done", "complete", "finished"]


class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强)

    新增特性:
    - completion_promise 检测：外部标志驱动退出
    - 可选上下文重置：防止上下文漂移
    - 防无限循环上限：迭代和时间双重保护
    """

    IDLE_TIMEOUT = 2 * 60 * 60  # 2小时（秒）

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable[[str], None] | Callable[[str], Coroutine[Any, Any, None]] | None = None
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
        # 状态持久化：使用唯一标识符避免多实例冲突
        self._instance_id: str = uuid.uuid4().hex[:8]
        self._state_file: Path = SEED_DIR / "ralph" / f"autonomous_{self._instance_id}_state.json"
        self._load_sop()

    def _load_sop(self) -> None:
        """加载自主探索 SOP"""
        if SOP_PATH.exists():
            with open(SOP_PATH, "r", encoding="utf-8") as f:
                self._sop_content = f.read()
            logger.info(f"Loaded autonomous SOP from {SOP_PATH}")
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
            logger.warning(f"SOP file not found: {SOP_PATH} - autonomous exploration disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._idle_monitor_loop())
        logger.warning("Autonomous explorer started")

    async def stop(self):
        """停止空闲监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.warning("Autonomous explorer stopped")

    async def _idle_monitor_loop(self):
        """空闲监控循环"""
        while self._running:
            idle_time = self.get_idle_time()

            if idle_time >= self.IDLE_TIMEOUT:
                logger.warning(f"Idle for {idle_time/60:.1f} minutes, starting autonomous exploration")
                result = await self._execute_autonomous_task()
                if result:
                    self.record_activity()  # 仅成功时重置计时
                else:
                    logger.warning("Autonomous exploration failed, not resetting idle timer")

            # 每30秒检查一次
            await asyncio.sleep(30)

    # === Ralph Loop 增强方法 ===

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志（Ralph Loop 核心机制）"""
        if COMPLETION_PROMISE_FILE.exists():
            content = COMPLETION_PROMISE_FILE.read_text().strip()
            if content in COMPLETION_PROMISE_TOKENS:
                logger.info(f"Completion promise detected: {content}")
                # 清除标志
                COMPLETION_PROMISE_FILE.unlink()
                return True
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
        """条件性重置上下文（防止上下文漂移，使用共享模块）"""
        if not CONTEXT_RESET_ENABLED:
            return None

        # 提取关键上下文
        preserved = extract_critical_context(self.agent.history)

        # 使用共享模块执行重置
        did_reset = reset_context(
            history=self.agent.history,
            iteration=self._iteration_count,
            reset_interval=CONTEXT_RESET_INTERVAL,
            preserved_context=preserved,
        )

        return preserved if did_reset else None

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
        """执行自主探索任务（复用 Agent Loop + Ralph Loop 增强）"""
        if not self._sop_content:
            logger.warning("No SOP loaded, skipping autonomous exploration")
            return None

        self._load_or_init_state()
        todo_content = self._load_todo_content()
        prompt = self._build_autonomous_prompt(todo_content, bool(todo_content))
        logger.info("Starting autonomous exploration via Agent Loop (Ralph enhanced)")

        original_system_prompt = self.agent.system_prompt
        original_history = list(self.agent.history)
        original_max_iterations = self.agent.max_iterations

        try:
            response = None
            self.agent.system_prompt = prompt
            self.agent.max_iterations = 100
            response = await self._run_ralph_loop()

            if response:
                logger.info(f"Autonomous exploration completed, response length: {len(response)}")
                if self.on_explore_complete:
                    if asyncio.iscoroutinefunction(self.on_explore_complete):
                        await self.on_explore_complete(response)
                    else:
                        self.on_explore_complete(response)
                return response
            else:
                logger.warning("Autonomous exploration returned empty response")
                return None

        except Exception as e:
            logger.exception(f"Autonomous exploration failed: {e}")
            self._persist_state(str(e))
            return None
        finally:
            self.agent.system_prompt = original_system_prompt
            self.agent.history = original_history
            self.agent.max_iterations = original_max_iterations

    def _load_todo_content(self) -> str:
        """加载TODO文件内容"""
        todo_path = SEED_DIR / "TODO.md"
        if todo_path.exists():
            with open(todo_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    async def _run_ralph_loop(self) -> str | None:
        """执行Ralph Loop主循环"""
        response: str | None = None  # Initialize before loop to avoid UnboundLocalError
        while True:
            self._iteration_count += 1

            if self._check_safety_limits():
                logger.info("Ralph Loop safety limit reached, cleaning up state for next session")
                self._cleanup_state()  # 清理状态，防止下次启动时立即达到上限
                break

            if self._check_completion_promise():
                logger.info("Completion promise detected, exiting Ralph loop")
                self._cleanup_state()
                await self._notify_completion("DONE")
                return "DONE"

            await self._reset_context_if_needed()
            try:
                response = await self.agent.run("继续执行自主探索任务")
            except Exception as e:
                logger.error(f"Agent execution failed at iteration {self._iteration_count}: {type(e).__name__}: {e}")
                response = f"Error: {e!s}"
            self._persist_state(response or "")

            if response and any(marker in response for marker in COMPLETION_MARKERS):
                logger.info(f"Autonomous exploration completed at iteration {self._iteration_count}")
                self._cleanup_state()
                break

            await self._handle_response(response)
            await asyncio.sleep(2)

        return response

    async def _notify_completion(self, result: str):
        """通知探索完成"""
        if self.on_explore_complete:
            if asyncio.iscoroutinefunction(self.on_explore_complete):
                await self.on_explore_complete(result)
            else:
                self.on_explore_complete(result)

    async def _handle_response(self, response: str | None):
        """处理agent响应"""
        if not response:
            self._empty_response_count += 1
            logger.warning(f"Empty response at iteration {self._iteration_count} "
                           f"(count: {self._empty_response_count})")
            if self._empty_response_count >= 3:
                logger.warning("Too many empty responses, trying simplified prompt")
                self.agent.history.append({"role": "user", "content": "请报告当前状态"})
            else:
                prompt = self._sop_content or ""
                self.agent.history.append({"role": "user", "content": prompt})

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
                available_tools=getattr(self.agent.tools, "get_tool_names", lambda: None)()
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

        # 构建 SOP 内容
        sop_prompt = f"""## 自主探索 SOP

{self._sop_content}

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
        prompt_parts = [
            "# 自主探索任务触发",
            "",
            "当前空闲2小时，开始执行自主任务。",
            "",
            "## 当前状态",
            f"- TODO状态: {'有待执行任务' if has_todo else '无TODO，进入规划模式'}",
            "",
        ]

        if has_todo and todo_content.strip():
            prompt_parts.extend([
                "## 当前TODO内容",
                todo_content,
                "",
                "请按照 SOP 执行流程，逐个完成 TODO 条目：",
                "1. 在 <thinking> 内推演执行逻辑",
                "2. 执行任务并记录到工作记忆",
                "3. 完成后标记 TODO 并更新工作记忆",
                "",
            ])
        else:
            prompt_parts.extend([
                "## 规划模式",
                "当前无TODO，请进入规划模式：",
                "1. 读取 history.md 和工作记忆",
                "2. 反思低价值操作，提炼进化线索",
                "3. 产出5-7条TODO（格式：`[ ] 类型 | 目标 | 验收标准 | 预期沉淀`）",
                "4. 更新 TODO.md 文件",
                "",
            ])

        prompt_parts.extend([
            "## SOP 核心原则",
            "- 价值公式：实际执行可落地性 × 进化沉淀价值",
            "- 不推诿、有逻辑、重沉淀",
            "- 失败升级：1次重试，2次探测，3次换方案",
            "- 不可逆操作需先确认用户（但自主模式下跳过需确认的操作）",
            "",
            "请开始执行自主探索任务。",
        ])

        return "\n".join(prompt_parts)


async def create_autonomous_explorer(agent_loop, on_explore_complete: Callable | None = None) -> AutonomousExplorer:
    """创建自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer
