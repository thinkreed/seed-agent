"""
Ralph Loop 状态管理模块

处理状态持久化和安全检查逻辑。
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("seed_agent.ralph")


class StateManager:
    """状态持久化管理器"""

    def __init__(self, state_file: Path):
        self._state_file = state_file

    def ensure_dir_exists(self) -> None:
        """确保状态目录存在"""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

    def load_or_init(self) -> dict[str, Any]:
        """加载或初始化状态"""
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")

        return {
            "iteration": 0,
            "start_time": time.time(),
            "accumulated_duration": 0,
        }

    def persist(
        self,
        iteration: int,
        start_time: float,
        accumulated_duration: float,
        response: str,
        task_file: str,
        completion_type: str,
    ) -> None:
        """持久化当前状态"""
        state = {
            "iteration": iteration,
            "start_time": start_time,
            "accumulated_duration": accumulated_duration + (time.time() - start_time),
            "last_response": response[:500] if response else "",
            "task_file": task_file,
            "completion_type": completion_type,
            "updated_at": time.time(),
        }

        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist state: {e}")

    def cleanup(self) -> None:
        """清理状态文件"""
        try:
            if self._state_file.exists():
                self._state_file.unlink()
        except OSError:
            pass


class SafetyChecker:
    """安全检查器"""

    def check_limits(
        self,
        iteration: int,
        max_iterations: int,
        start_time: float,
        accumulated_duration: float,
        max_duration: int,
    ) -> bool:
        """检查安全上限

        Returns:
            True 表示达到上限应停止
        """
        # 迭代上限
        if iteration >= max_iterations:
            logger.warning(f"Reached max iterations: {iteration}/{max_iterations}")
            return True

        # 时间上限
        current_duration = accumulated_duration + (time.time() - start_time)
        if current_duration >= max_duration:
            logger.warning(
                f"Reached max duration: {current_duration:.0f}s/{max_duration}s"
            )
            return True

        return False

    def generate_status_report(
        self,
        task_file: str,
        iteration: int,
        start_time: float,
        accumulated_duration: float,
        completion_type: str,
        state_file: Path,
    ) -> str:
        """生成状态报告"""
        current_duration = accumulated_duration + (time.time() - start_time)

        return (
            f"Ralph Loop Status Report\n"
            f"========================\n"
            f"Task: {task_file}\n"
            f"Completion Type: {completion_type}\n"
            f"Iterations: {iteration}\n"
            f"Duration: {current_duration:.0f}s\n"
            f"State File: {state_file}\n"
            f"========================"
        )