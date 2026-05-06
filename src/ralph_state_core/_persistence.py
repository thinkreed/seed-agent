"""
持久化函数

提供状态持久化、加载和清理功能。
"""

import json
import logging
import time
from pathlib import Path

from src.ralph_state_core._types import RalphState

logger = logging.getLogger("seed_agent.ralph")


def persist_state(
    state_file: Path,
    iteration: int,
    start_time: float,
    accumulated_duration: float,
    response: str = "",
    task_file: str = "",
    completion_type: str = "",
) -> None:
    """
    持久化当前状态到 JSON 文件

    Args:
        state_file: 状态文件路径
        iteration: 当前迭代次数
        start_time: 当前会话开始时间
        accumulated_duration: 累计执行时间（跨会话）
        response: 最后响应内容
        task_file: 任务文件路径
        completion_type: 完成类型
    """
    # 确保目录存在
    state_file.parent.mkdir(parents=True, exist_ok=True)

    # 计算当前会话已执行时间，累加到总时间
    current_elapsed = time.time() - start_time if start_time > 0 else 0
    total_accumulated = accumulated_duration + current_elapsed

    state_data = {
        "iteration": iteration,
        "accumulated_duration": total_accumulated,
        "start_time": start_time,
        "last_response": response[:500] if response else "",
        "timestamp": time.time(),
        "task_file": task_file,
        "completion_type": completion_type,
    }

    state_file.write_text(json.dumps(state_data, indent=2))
    logger.debug(
        f"State persisted: iteration={iteration}, accumulated={total_accumulated}s"
    )


def load_or_init_state(
    state_file: Path,
    default_accumulated: float = 0.0,
) -> RalphState:
    """
    从 JSON 文件加载或初始化状态

    Args:
        state_file: 状态文件路径
        default_accumulated: 默认累计时间

    Returns:
        RalphState 实例
    """
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            state = RalphState.from_dict(data)
            logger.info(
                f"Resumed Ralph Loop from iteration {state.iteration}, "
                f"accumulated: {state.accumulated_duration}s"
            )
            return state
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                f"State file corrupted, starting fresh: {type(e).__name__}: {e}"
            )

    # 初始化新状态
    return RalphState(
        iteration=0,
        accumulated_duration=default_accumulated,
        start_time=time.time(),
    )


def cleanup_state_file(state_file: Path) -> None:
    """
    清理状态文件

    Args:
        state_file: 状态文件路径
    """
    if state_file.exists():
        state_file.unlink()
        logger.info("State file cleaned up")


def generate_status_report(
    task_file: str,
    iteration: int,
    start_time: float,
    accumulated_duration: float,
    completion_type: str,
    state_file: Path,
    exit_reason: str = "Safety limit reached",
) -> str:
    """
    生成状态报告

    Args:
        task_file: 任务文件路径
        iteration: 当前迭代次数
        start_time: 当前会话开始时间
        accumulated_duration: 累计执行时间
        completion_type: 完成类型
        state_file: 状态文件路径
        exit_reason: 退出原因

    Returns:
        格式化的状态报告
    """
    current_elapsed = time.time() - start_time
    total_elapsed = accumulated_duration + current_elapsed

    report = f"""
Ralph Loop Status Report:
- Task: {task_file}
- Iterations: {iteration}
- Total Duration: {total_elapsed / 60:.1f} minutes (accumulated: {accumulated_duration / 60:.1f} min)
- Exit Reason: {exit_reason}
- Completion Type: {completion_type}
- State File: {state_file}
"""
    logger.info(report)
    return report