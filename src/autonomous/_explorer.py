"""自主探索模块：空闲时根据 SOP 执行自主任务

增强版 (Ralph Loop + Memory Graph 集成):
- completion_promise 检测：外部完成标志驱动退出
- 可选上下文重置：防止上下文漂移
- 防无限循环上限：迭代和时间双重保护
- Memory Graph 选择：基于历史结果选择最佳 Skill
- 自动结果记录：执行完成后自动记录 outcome
- Session 事件记录：所有状态变更通过 Session 正确记录

重构后架构（子模块化）:
- _idle_monitor: 空闲监控
- _sop_loader: SOP 加载
- _prompt_builder: Prompt 构建
- _task_executor: 任务执行
- _state_manager: 状态管理
- _defense: 四层防御

主文件保留 AutonomousExplorer 类骨架和公共 API，向后兼容。
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.ralph_state import _ensure_ralph_dir

# 导入子模块（使用相对导入）
from ._defense import (
    DefenseState,
    check_completion_promise,
)
from ._idle_monitor import IdleMonitor
from ._prompt_builder import (
    build_autonomous_prompt,
    build_task_instruction,
    extract_autonomous_prompt_core,
    extract_task_signals,
)
from ._sop_loader import (
    expand_sop_paths,
    get_project_root,
    get_sop_path,
    load_sop,
)
from ._state_manager import (
    StateManager,
    TodoCache,
    extract_critical_context,
)
from ._task_executor import (
    COMPLETION_MARKERS,
    CONTEXT_RESET_ENABLED,
    CONTEXT_RESET_INTERVAL,
    RALPH_MAX_DURATION,
    RALPH_MAX_ITERATIONS,
    TaskExecutor,
)

from src.shared_config import get_autonomous_config, get_seed_dir_with_fallback

logger = logging.getLogger("seed_agent")


def _get_completion_promise_file() -> Path:
    """获取完成标志文件路径（动态）"""
    return _ensure_ralph_dir().parent / "completion_promise"


class AutonomousExplorer:
    """自主探索执行器 (Ralph Loop 增强 + 四层防御体系)

    重构后：组合使用子模块，保持向后兼容的公共 API。

    多层防御体系（方案 A+C 整合）：
    - Layer 1: 预算警告注入（70%/90%阈值）
    - Layer 2: 进度检测窗口（空转循环识别）
    - Layer 3: 时间断路器（单任务时间上限）
    - Layer 4: 递减重试预算（失败重试递减）
    - 安全上限: 1000轮 + 8小时（继承 RalphLoop）
    """

    def __init__(
        self,
        agent_loop: "AgentLoop",
        on_explore_complete: Callable[[str], None]
        | Callable[[str], Coroutine[Any, Any, None]]
        | None = None,
    ):
        self.agent = agent_loop
        self.on_explore_complete = on_explore_complete

        # 组合子模块
        self._idle_monitor = IdleMonitor(
            idle_timeout=get_autonomous_config().idle_timeout_hours * 60 * 60
        )
        self._task_executor = TaskExecutor(agent_loop, on_explore_complete)

        # 配置
        self._config = get_autonomous_config()

        # 向后兼容的属性（从子模块暴露）
        self._sop_content: str | None = load_sop()

    # === 向后兼容属性访问器 ===

    @property
    def _last_activity(self) -> float:
        """向后兼容：上次活动时间"""
        return self._idle_monitor._last_activity

    @property
    def _running(self) -> bool:
        """向后兼容：监控是否运行"""
        return self._idle_monitor._running

    @property
    def _idle_timeout(self) -> float:
        """向后兼容：空闲超时时间"""
        return self._idle_monitor._idle_timeout

    @property
    def _iteration_count(self) -> int:
        """向后兼容：迭代计数"""
        return self._task_executor._state_manager.get_iteration_count()

    @_iteration_count.setter
    def _iteration_count(self, value: int) -> None:
        """向后兼容：设置迭代计数"""
        self._task_executor._state_manager.set_iteration_count(value)

    @property
    def _ralph_start_time(self) -> float:
        """向后兼容：会话开始时间"""
        return self._task_executor._state_manager.get_start_time()

    @_ralph_start_time.setter
    def _ralph_start_time(self, value: float) -> None:
        """向后兼容：设置会话开始时间"""
        self._task_executor._state_manager.set_start_time(value)

    @property
    def _accumulated_duration(self) -> float:
        """向后兼容：累计执行时间"""
        return self._task_executor._state_manager.get_accumulated_duration()

    @_accumulated_duration.setter
    def _accumulated_duration(self, value: float) -> None:
        """向后兼容：设置累计执行时间"""
        self._task_executor._state_manager.set_accumulated_duration(value)

    @property
    def _empty_response_count(self) -> int:
        """向后兼容：空响应计数"""
        return self._task_executor._state_manager.get_empty_response_count()

    @_empty_response_count.setter
    def _empty_response_count(self, value: int) -> None:
        """向后兼容：设置空响应计数"""
        self._task_executor._state_manager._empty_response_count = value

    @property
    def _state_file(self) -> Path:
        """向后兼容：状态文件路径"""
        return self._task_executor._state_manager.get_state_file()

    @_state_file.setter
    def _state_file(self, value: Path) -> None:
        """向后兼容：设置状态文件路径"""
        self._task_executor._state_manager._state_file = value

    @property
    def _task_start_time(self) -> float:
        """向后兼容：任务开始时间"""
        return self._task_executor._defense._task_start_time

    @_task_start_time.setter
    def _task_start_time(self, value: float) -> None:
        """向后兼容：设置任务开始时间"""
        self._task_executor._defense._task_start_time = value

    @property
    def _action_history(self) -> list[dict[str, Any]]:
        """向后兼容：工具调用历史"""
        return self._task_executor._defense._action_history

    @_action_history.setter
    def _action_history(self, value: list[dict[str, Any]]) -> None:
        """向后兼容：设置工具调用历史"""
        self._task_executor._defense._action_history = value

    @property
    def _retry_count(self) -> int:
        """向后兼容：重试计数"""
        return self._task_executor._defense.get_retry_count()

    @_retry_count.setter
    def _retry_count(self, value: int) -> None:
        """向后兼容：设置重试计数"""
        self._task_executor._defense._retry_count = value

    @property
    def _budget_warning_sent(self) -> bool:
        """向后兼容：预算警告已发送"""
        return self._task_executor._defense._budget_warning_sent

    @_budget_warning_sent.setter
    def _budget_warning_sent(self, value: bool) -> None:
        """向后兼容：设置预算警告状态"""
        self._task_executor._defense._budget_warning_sent = value

    @property
    def _budget_urgent_sent(self) -> bool:
        """向后兼容：紧急预算警告已发送"""
        return self._task_executor._defense._budget_urgent_sent

    @_budget_urgent_sent.setter
    def _budget_urgent_sent(self, value: bool) -> None:
        """向后兼容：设置紧急预算警告状态"""
        self._task_executor._defense._budget_urgent_sent = value

    @property
    def _time_warning_sent(self) -> bool:
        """向后兼容：时间警告已发送"""
        return self._task_executor._defense._time_warning_sent

    @_time_warning_sent.setter
    def _time_warning_sent(self, value: bool) -> None:
        """向后兼容：设置时间警告状态"""
        self._task_executor._defense._time_warning_sent = value

    @property
    def _task(self) -> asyncio.Task[None] | None:
        """向后兼容：监控任务"""
        return self._idle_monitor._task

    # === 公共 API（向后兼容）===

    def record_activity(self) -> None:
        """记录用户活动时间"""
        self._idle_monitor.record_activity()
        # 同步到 task_executor（如果需要）
        self._task_executor._state_manager._ralph_start_time = 0.0

    def get_idle_time(self) -> float:
        """获取当前空闲时间（秒）"""
        return self._idle_monitor.get_idle_time()

    async def start(self) -> None:
        """启动空闲监控"""
        if not self._sop_content:
            logger.warning(
                f"SOP file not found: {get_sop_path()} - autonomous exploration disabled"
            )
            return

        async def on_idle():
            return await self._task_executor.execute_autonomous_task()

        # 启动空闲监控，传入回调
        self._idle_monitor._running = True
        self._idle_monitor._task = asyncio.create_task(
            self._idle_monitor._idle_monitor_loop(on_idle)
        )
        logger.warning("Autonomous explorer started")

    async def stop(self) -> None:
        """停止空闲监控"""
        await self._idle_monitor.stop()

    # === 内部方法（向后兼容，委托给子模块）===

    def _load_sop(self) -> None:
        """加载自主探索 SOP（向后兼容）"""
        self._sop_content = load_sop()

    def _check_completion_promise(self) -> bool:
        """检查外部完成标志"""
        return check_completion_promise(_get_completion_promise_file())

    def _check_safety_limits(self) -> bool:
        """检查安全上限"""
        return self._task_executor._check_safety_limits()

    def _get_retry_budget(self) -> int:
        """获取重试预算"""
        return self._task_executor._defense.get_retry_budget()

    async def _inject_budget_warning(self, current: int, max_budget: int) -> None:
        """注入预算警告"""
        await self._task_executor._defense.inject_budget_warning(
            current, max_budget, self.agent
        )

    def _check_progress_window(self) -> bool:
        """检查进度窗口"""
        return self._task_executor._defense.check_progress_window()

    def _check_time_circuit_breaker(self) -> bool:
        """检查时间断路器"""
        return self._task_executor._defense.check_time_circuit_breaker(self.agent)

    def _reset_defense_state(self) -> None:
        """重置防御状态"""
        self._task_executor._defense.reset()

    def _extract_critical_context(self) -> str | None:
        """提取关键上下文"""
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
        # 每次调用时动态获取路径，确保 mock 能生效
        seed_dir = get_seed_dir_with_fallback()
        return self._task_executor._todo_cache.load_todo_content(seed_dir)

    def _build_autonomous_prompt(self, todo_content: str, has_todo: bool) -> str:
        """构建自主探索 prompt"""
        return self._task_executor._build_full_prompt(todo_content)

    def _extract_task_signals(self, todo_content: str, has_todo: bool) -> list[str]:
        """提取任务信号"""
        return extract_task_signals(todo_content, has_todo)

    def _build_task_instruction(self, todo_content: str, has_todo: bool) -> str:
        """构建任务指令"""
        return build_task_instruction(todo_content, has_todo, get_seed_dir_with_fallback())

    def _extract_autonomous_prompt_core(self, full_prompt: str) -> str:
        """提取 prompt 核心"""
        return extract_autonomous_prompt_core(full_prompt, self._sop_content)

    async def _execute_autonomous_task(self) -> str | None:
        """执行自主探索任务"""
        return await self._task_executor.execute_autonomous_task()

    async def _run_ralph_loop(self, max_budget: int | None = None) -> str | None:
        """执行 Ralph Loop"""
        return await self._task_executor._run_ralph_loop(max_budget)

    async def _handle_response(self, response: str | None) -> str | None:
        """处理响应并返回下一轮的 prompt（向后兼容）"""
        return await self._task_executor._handle_response(response)


async def create_autonomous_explorer(
    agent_loop: "AgentLoop",
    on_explore_complete: Callable[[str], None] | None = None,
) -> AutonomousExplorer:
    """创建自主探索器"""
    explorer = AutonomousExplorer(agent_loop, on_explore_complete)
    await explorer.start()
    return explorer