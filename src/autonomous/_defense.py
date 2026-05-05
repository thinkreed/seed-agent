"""四层防御模块

提供四层防御体系功能:
- Layer 1: 预算警告注入（70%/90%阈值）
- Layer 2: 进度检测窗口（空转循环识别）
- Layer 3: 时间断路器（单任务时间上限）
- Layer 4: 递减重试预算（失败重试递减）

从 AutonomousExplorer 中提取，保持接口不变。
"""

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.shared_config import get_autonomous_config

logger = logging.getLogger("seed_agent")


class DefenseState:
    """四层防御状态

    管理所有防御机制的状态变量。
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
            - 第1次重试: 100% 基础预算
            - 第2次重试: 50% 基础预算
            - 第3次重试: 25% 基础预算
            - 超过上限: 0（不再执行）
        """
        base_budget = self._config.max_iterations_per_task

        if self._retry_count >= len(self._config.retry_decay_factors):
            logger.warning(
                f"Retry count {self._retry_count} exceeds max "
                f"{len(self._config.retry_decay_factors)}, returning 0 budget"
            )
            return 0

        decay_factor = self._config.retry_decay_factors[self._retry_count]
        budget = int(base_budget * decay_factor)
        logger.info(
            f"Retry budget: base={base_budget}, retry={self._retry_count}, "
            f"factor={decay_factor}, budget={budget}"
        )
        return budget

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
        """注入预算警告消息

        在剩余预算达到阈值时，注入警告消息到 Agent 对话历史，
        让 Agent 能够感知剩余预算并主动规划收尾。

        Args:
            current: 当前已使用的迭代次数
            max_budget: 最大迭代次数预算
            agent: AgentLoop 实例（用于注入消息）
        """
        percentage = current / max_budget * 100

        # 70% 预算警告（仅发送一次）
        if (
            percentage >= self._config.budget_warning_threshold * 100
            and not self._budget_warning_sent
        ):
            remaining = max_budget - current
            warning_msg = (
                f"[BUDGET WARNING] 已使用 {current}/{max_budget} 轮迭代 ({percentage:.0f}%)。"
                f"剩余 {remaining} 轮。建议开始总结和收尾工作。"
            )
            agent.inject_system_message(warning_msg)
            self._budget_warning_sent = True
            logger.info(f"Budget warning injected at {percentage:.0f}%")

        # 90% 紧急警告（仅发送一次）
        if (
            percentage >= self._config.budget_urgent_threshold * 100
            and not self._budget_urgent_sent
        ):
            remaining = max_budget - current
            urgent_msg = (
                f"[BUDGET URGENT] 已使用 {current}/{max_budget} 轮 ({percentage:.0f}%)。"
                f"仅剩 {remaining} 轮。请立即执行最终操作。"
            )
            agent.inject_system_message(urgent_msg)
            self._budget_urgent_sent = True
            logger.warning(f"Budget urgent warning injected at {percentage:.0f}%")

    # === Layer 2: 进度检测窗口 ===

    def check_progress_window(self) -> bool:
        """检查进度窗口，判断是否有有效进展

        检测连续 N 轮无有效工具调用，判定为"空转循环"。

        Returns:
            True: 有进展，继续执行
            False: 无进展，建议终止（空转循环）
        """
        window_size = self._config.progress_detection_window

        # 获取最近 N 轮的工具调用记录
        recent_actions = self._action_history[-window_size:]

        # 检查是否有实质性工具调用（排除 ask_user, search_history 等）
        meaningful_actions = [
            a for a in recent_actions
            if a.get("tool") in self._config.meaningful_tools
        ]

        if len(meaningful_actions) == 0 and len(recent_actions) >= window_size:
            logger.warning(f"连续 {window_size} 轮无有效工具调用，判定为空转循环")
            return False

        return True

    # === Layer 3: 时间断路器 ===

    def check_time_circuit_breaker(
        self,
        agent: "AgentLoop",
    ) -> bool:
        """检查时间断路器

        单任务时间上限，防止长时间无产出运行。

        Args:
            agent: AgentLoop 实例（用于注入警告）

        Returns:
            True: 未超时，继续执行
            False: 超时，强制终止
        """
        elapsed = time.time() - self._task_start_time
        max_duration = self._config.max_duration_per_task

        if elapsed >= max_duration:
            logger.warning(
                f"任务执行时间 {elapsed:.0f}s 超过上限 {max_duration}s，触发断路器"
            )
            return False

        # 在 80% 时间时注入时间警告（仅发送一次）
        if (
            elapsed >= max_duration * self._config.time_warning_threshold
            and not self._time_warning_sent
        ):
            remaining = max_duration - elapsed
            warning_msg = (
                f"[TIME WARNING] 已运行 {elapsed:.0f}s，剩余 {remaining:.0f}s。"
                f"请尽快完成当前操作。"
            )
            agent.inject_system_message(warning_msg)
            self._time_warning_sent = True
            logger.info(f"Time warning injected at {elapsed:.0f}s")

        return True

    def get_task_elapsed_time(self) -> float:
        """获取当前任务已执行时间"""
        return time.time() - self._task_start_time


# 完成检测锁（原子操作）
_completion_check_lock = threading.Lock()


def check_completion_promise(completion_file: Path) -> bool:
    """检查外部完成标志（Ralph Loop 核心机制，原子化版本）

    使用锁保护文件检查与删除操作，防止多进程/多线程竞态条件。

    Args:
        completion_file: 完成标志文件路径

    Returns:
        True 表示检测到完成标志
    """
    with _completion_check_lock:
        if completion_file.exists():
            try:
                content = completion_file.read_text().strip()
                if content in ["DONE", "COMPLETE", "TASK_FINISHED"]:
                    logger.info(f"Completion promise detected: {content}")
                    # 清除标志
                    completion_file.unlink()
                    return True
            except OSError as e:
                logger.warning(f"Failed to read/delete completion promise: {e}")
    return False