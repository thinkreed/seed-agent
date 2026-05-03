"""
Ralph Loop 共享状态管理模块

提供 RalphLoop 和 AutonomousExplorer 共享的状态管理逻辑:
- 安全上限检查 (迭代/时间双重保护)
- 状态持久化 (JSON 文件存储)
- 上下文重置 (防止漂移)
- 关键信息提取

避免代码重复，统一维护。
"""

import json
import logging
import time
from pathlib import Path

from src.shared_config import SEED_DIR

logger = logging.getLogger("seed_agent.ralph")

# 默认状态目录
RALPH_STATE_DIR = SEED_DIR / "ralph"


class RalphState:
    """Ralph Loop 状态数据类"""

    def __init__(
        self,
        iteration: int = 0,
        accumulated_duration: float = 0.0,
        start_time: float = 0.0,
        last_response: str = "",
        task_file: str = "",
        completion_type: str = "",
    ):
        self.iteration = iteration
        self.accumulated_duration = accumulated_duration
        self.start_time = start_time or time.time()
        self.last_response = last_response
        self.task_file = task_file
        self.completion_type = completion_type

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "iteration": self.iteration,
            "accumulated_duration": self.accumulated_duration,
            "start_time": self.start_time,  # 保存原始开始时间
            "last_response": self.last_response[:500] if self.last_response else "",
            "timestamp": time.time(),
            "task_file": self.task_file,
            "completion_type": self.completion_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RalphState":
        """从字典创建"""
        return cls(
            iteration=data.get("iteration", 0),
            accumulated_duration=data.get("accumulated_duration", 0),
            start_time=data.get("start_time", time.time()),  # 使用保存的开始时间
            last_response=data.get("last_response", ""),
            task_file=data.get("task_file", ""),
            completion_type=data.get("completion_type", ""),
        )


def check_safety_limits(
    iteration: int,
    max_iterations: int,
    start_time: float,
    accumulated_duration: float,
    max_duration: int,
) -> bool:
    """
    检查安全上限（迭代/时间双重保护）

    Args:
        iteration: 当前迭代次数
        max_iterations: 最大迭代次数
        start_time: 当前会话开始时间
        accumulated_duration: 累计执行时间（跨会话）
        max_duration: 最大执行时间（秒）

    Returns:
        True 表示达到上限，需要停止
    """
    # 迭代上限
    if iteration >= max_iterations:
        logger.warning(f"Ralph Loop exceeded max iterations ({max_iterations})")
        return True

    # 时间上限（累计 + 当前会话）
    if start_time > 0:
        current_elapsed = time.time() - start_time
        total_elapsed = accumulated_duration + current_elapsed
        if total_elapsed >= max_duration:
            logger.warning(
                f"Ralph Loop exceeded max duration ({max_duration}s, "
                f"accumulated: {accumulated_duration}s, current: {current_elapsed}s)"
            )
            return True

    return False


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
    久化当前状态到 JSON 文件

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
        "start_time": start_time,  # 保存原始开始时间，恢复时使用
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


def extract_critical_context(history: list[dict]) -> str | None:
    """
    从历史记录中提取关键上下文

    Args:
        history: 对话历史列表

    Returns:
        关键上下文摘要，或 None
    """
    if not history:
        return None

    # 提取最后一条 assistant 消息的摘要
    for msg in reversed(history):
        if msg.get("role") == "assistant" and msg.get("content"):
            return f"上次执行摘要: {msg['content'][:300]}"

    return None


def reset_context(
    history: list[dict],
    iteration: int,
    reset_interval: int,
    preserved_context: str | None = None,
) -> bool:
    """
    条件性重置上下文（防止漂移）

    Args:
        history: 对话历史列表（会被清空）
        iteration: 当前迭代次数
        reset_interval: 重置间隔
        preserved_context: 保留的关键上下文

    Returns:
        True 表示执行了重置
    """
    # 仅在指定间隔执行
    if iteration % reset_interval != 0:
        return False

    # 清空历史
    history.clear()

    # 重新注入保留信息（如有）
    if preserved_context:
        history.append(
            {
                "role": "system",
                "content": f"[迭代 {iteration} 状态摘要]\n{preserved_context}",
            }
        )

    logger.info(f"Context reset at iteration {iteration}")
    return True


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
