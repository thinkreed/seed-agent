"""四层防御模块

提供四层防御体系功能:
- Layer 1: 预算警告注入（70%/90%阈值）
- Layer 2: 进度检测窗口（空转循环识别）
- Layer 3: 时间断路器（单任务时间上限）
- Layer 4: 递减重试预算（失败重试递减）

API 兼容入口，具体实现委托给 _defense_budget 和 _defense_time 模块。
"""

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.autonomous._defense_budget import get_retry_budget, inject_budget_warning
from src.autonomous._defense_time import (
    check_completion_promise,
    check_progress_window,
    check_time_circuit_breaker,
)
from src.shared_config import get_autonomous_config


class DefenseState:
    """四层防御状态

    管理所有防御机制的状态变量，API 保持不变。
    """

    def __init__(self) -> None:
        """初始化防御状态"""
        # Layer 3: 时间断路器状态
        self._task_start_time: float = 0.0
        # Layer 2: 进度检测状态
        self._action_history: list[dict[str, Any]] = []
        # Layer 4: 重试状态
        self._retry_count: int = 0
        # Layer 1: 预算警告状态
        self._budget_warning_sent: bool = False
        self._budget_urgent_sent: bool = False
        # Layer 3: 时间警告状态
        self._time_warning_sent: bool = False

        self._config = get_autonomous_config()

    def reset(self) -> None:
        """重置所有防御状态（新任务开始时调用）"""
        self._task_start_time = time.time()
        self._action_history = []
        self._budget_warning_sent = False
        self._budget_urgent_sent = False
        self._time_warning_sent = False

    def add_action(self, tool_name: str, iteration: int) -> None:
        """添加工具调用记录

        Args:
            tool_name: 工具名称
            iteration: 当前迭代次数
        """
        self._action_history.append({
            "tool": tool_name,
            "iteration": iteration,
        })

    # === Layer 4: 递减重试预算 ===

    def get_retry_budget(self) -> int:
        """获取当前重试的迭代预算

        Returns:
            当前重试轮次的迭代上限
        """
        return get_retry_budget(
            self._retry_count,
            self._config.max_iterations_per_task,
            self._config.retry_decay_factors,
        )

    def increment_retry(self) -> None:
        """增加重试计数"""
        self._retry_count += 1

    def reset_retry(self) -> None:
        """重置重试计数"""
        self._retry_count = 0

    def get_retry_count(self) -> int:
        """获取当前重试计数"""
        return self._retry_count

    # === Layer 1: 预算警告注入 ===

    async def inject_budget_warning(
        self,
        current: int,
        max_budget: int,
        agent: "AgentLoop",
    ) -> None:
        """注入预算警告消息"""
        self._budget_warning_sent, self._budget_urgent_sent = await inject_budget_warning(
            current,
            max_budget,
            agent,
            self._config.budget_warning_threshold,
            self._config.budget_urgent_threshold,
            self._budget_warning_sent,
            self._budget_urgent_sent,
        )

    # === Layer 2: 进度检测窗口 ===

    def check_progress_window(self) -> bool:
        """检查进度窗口，判断是否有有效进展

        Returns:
            True: 有进展，继续执行
            False: 无进展，建议终止（空转循环）
        """
        return check_progress_window(
            self._action_history,
            self._config.progress_detection_window,
            self._config.meaningful_tools,
        )

    # === Layer 3: 时间断路器 ===

    def check_time_circuit_breaker(self, agent: "AgentLoop") -> bool:
        """检查时间断路器

        Returns:
            True: 未超时，继续执行
            False: 超时，强制终止
        """
        should_continue, self._time_warning_sent = check_time_circuit_breaker(
            self._task_start_time,
            self._config.max_duration_per_task,
            self._config.time_warning_threshold,
            self._time_warning_sent,
            agent,
        )
        return should_continue

    def get_task_elapsed_time(self) -> float:
        """获取当前任务已执行时间"""
        return time.time() - self._task_start_time


# 导出完成检测函数（保持 API 兼容）
__all__ = ["DefenseState", "check_completion_promise"]