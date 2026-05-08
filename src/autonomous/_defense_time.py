"""时间/进度相关防御模块

提供时间和进度管理功能:
- Layer 2: 进度检测窗口（空转循环识别）
- Layer 3: 时间断路器（单任务时间上限）
- 完成检测：外部标志文件检查

从 _defense.py 拆分，支持 DefenseState 调用。
"""

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")

# 完成检测锁（原子操作）
_completion_check_lock = threading.Lock()


# === Layer 2: 进度检测窗口 ===


def check_progress_window(
    action_history: list[dict[str, Any]],
    progress_detection_window: int,
    meaningful_tools: set[str],
) -> bool:
    """检查进度窗口，判断是否有有效进展

    检测连续 N 轮无有效工具调用，判定为"空转循环"。

    Args:
        action_history: 工具调用历史记录
        progress_detection_window: 检测窗口大小
        meaningful_tools: 有效工具集合

    Returns:
        True: 有进展，继续执行
        False: 无进展，建议终止（空转循环）
    """
    # 获取最近 N 轮的工具调用记录
    recent_actions = action_history[-progress_detection_window:]

    # 检查是否有实质性工具调用
    meaningful_actions = [
        a for a in recent_actions if a.get("tool") in meaningful_tools
    ]

    if len(meaningful_actions) == 0 and len(recent_actions) >= progress_detection_window:
        logger.warning(f"连续 {progress_detection_window} 轮无有效工具调用，判定为空转循环")
        return False

    return True


# === Layer 3: 时间断路器 ===


def check_time_circuit_breaker(
    task_start_time: float,
    max_duration_per_task: float,
    time_warning_threshold: float,
    time_warning_sent: bool,
    agent: "AgentLoop",
) -> tuple[bool, bool]:
    """检查时间断路器

    单任务时间上限，防止长时间无产出运行。

    Args:
        task_start_time: 任务开始时间戳
        max_duration_per_task: 最大执行时长（秒）
        time_warning_threshold: 时间警告阈值（如 0.8 表示 80%）
        time_warning_sent: 是否已发送时间警告
        agent: AgentLoop 实例（用于注入警告）

    Returns:
        (should_continue, new_time_warning_sent)
        - should_continue: True 未超时继续，False 超时终止
        - new_time_warning_sent: 更新后的警告状态
    """
    elapsed = time.time() - task_start_time

    if elapsed >= max_duration_per_task:
        logger.warning(
            f"任务执行时间 {elapsed:.0f}s 超过上限 {max_duration_per_task}s，触发断路器"
        )
        return False, time_warning_sent

    # 在阈值时间时注入时间警告（仅发送一次）
    if elapsed >= max_duration_per_task * time_warning_threshold and not time_warning_sent:
        remaining = max_duration_per_task - elapsed
        warning_msg = (
            f"[TIME WARNING] 已运行 {elapsed:.0f}s，剩余 {remaining:.0f}s。"
            f"请尽快完成当前操作。"
        )
        agent.inject_system_message(warning_msg)
        logger.info(f"Time warning injected at {elapsed:.0f}s")
        time_warning_sent = True

    return True, time_warning_sent


# === 完成检测 ===


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