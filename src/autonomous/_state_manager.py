"""状态管理模块

提供状态持久化和恢复功能:
- load_state: 加载状态文件
- persist_state: 持久化当前状态
- cleanup_state: 清理状态文件
- load_todo_content: 加载 TODO 文件内容（带缓存）

从 AutonomousExplorer 中提取，保持接口不变。
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from src.ralph_state import (
    RalphState,
    cleanup_state_file,
    load_or_init_state,
    persist_state as ralph_persist_state,
)
from src.shared_config import get_seed_dir_with_fallback

logger = logging.getLogger("seed_agent")

# Ralph Loop 增强配置
RALPH_MAX_ITERATIONS = 1000  # 理论上限（安全兜底）


class StateManager:
    """状态管理器

    管理 Ralph Loop 的状态持久化、恢复和清理。
    """

    # 固定状态文件名，进程重启后可恢复
    STATE_FILE_NAME = "autonomous_state.json"

    def __init__(self, state_file: Path | None = None):
        """初始化状态管理器

        Args:
            state_file: 状态文件路径（可选，默认使用固定名称）
        """
        if state_file is None:
            seed_dir = get_seed_dir_with_fallback()
            state_file = seed_dir / "ralph" / self.STATE_FILE_NAME

        self._state_file = state_file

        # 状态变量
        self._iteration_count: int = 0
        self._ralph_start_time: float = 0.0
        self._accumulated_duration: float = 0.0
        self._empty_response_count: int = 0

    def load_or_init_state(self) -> None:
        """加载或初始化状态

        如果加载的状态已达到迭代上限，则重置状态开始新会话。
        """
        state = load_or_init_state(self._state_file)

        # 如果迭代次数已达到上限，重置状态开始新会话
        if state.iteration >= RALPH_MAX_ITERATIONS:
            logger.warning(
                f"Loaded state has reached max iterations ({state.iteration}/{RALPH_MAX_ITERATIONS}), "
                "resetting for new session"
            )
            self.cleanup_state()  # 清理旧状态文件
            state = RalphState()  # 重新初始化

        self._iteration_count = state.iteration
        self._accumulated_duration = state.accumulated_duration
        self._ralph_start_time = state.start_time
        self._empty_response_count = 0  # 重置空响应计数

    def persist_state(self, response: str = "") -> None:
        """持久化当前状态

        Args:
            response: 最后响应内容
        """
        ralph_persist_state(
            state_file=self._state_file,
            iteration=self._iteration_count,
            start_time=self._ralph_start_time,
            accumulated_duration=self._accumulated_duration,
            response=response,
        )

    def cleanup_state(self) -> None:
        """清理状态文件"""
        cleanup_state_file(self._state_file)

    def get_iteration_count(self) -> int:
        """获取当前迭代次数"""
        return self._iteration_count

    def increment_iteration(self) -> int:
        """增加迭代次数并返回新值"""
        self._iteration_count += 1
        return self._iteration_count

    def set_iteration_count(self, count: int) -> None:
        """设置迭代次数"""
        self._iteration_count = count

    def get_start_time(self) -> float:
        """获取当前会话开始时间"""
        return self._ralph_start_time

    def set_start_time(self, time_val: float) -> None:
        """设置开始时间"""
        self._ralph_start_time = time_val

    def get_accumulated_duration(self) -> float:
        """获取累计执行时间"""
        return self._accumulated_duration

    def set_accumulated_duration(self, duration: float) -> None:
        """设置累计执行时间"""
        self._accumulated_duration = duration

    def get_empty_response_count(self) -> int:
        """获取空响应计数"""
        return self._empty_response_count

    def increment_empty_response(self) -> None:
        """增加空响应计数"""
        self._empty_response_count += 1

    def reset_empty_response_count(self) -> None:
        """重置空响应计数"""
        self._empty_response_count = 0

    def get_state_file(self) -> Path:
        """获取状态文件路径"""
        return self._state_file


class TodoCache:
    """TODO 文件缓存

    缓存策略：30秒内不重复读取文件，减少 I/O 开销。
    """

    def __init__(self, ttl: float = 30.0):
        """初始化 TODO 缓存

        Args:
            ttl: 缓存有效期（秒）
        """
        self._cache: str | None = None
        self._cache_time: float = 0.0
        self._cache_seed_dir: Path | None = None  # 记录缓存对应的 seed_dir
        self._ttl: float = ttl

    def load_todo_content(self, seed_dir: Path) -> str:
        """加载TODO文件内容（带 TTL 缓存）

        Args:
            seed_dir: 主工作目录路径

        Returns:
            TODO 文件内容，或空字符串
        """
        now = time.time()

        # 缓存有效且 seed_dir 相同，直接返回
        if (
            self._cache is not None
            and now - self._cache_time < self._ttl
            and self._cache_seed_dir == seed_dir
        ):
            return self._cache

        todo_path = seed_dir / "TODO.md"
        if todo_path.exists():
            try:
                with open(todo_path, encoding="utf-8") as f:
                    content = f.read()
                # 更新缓存
                self._cache = content
                self._cache_time = now
                self._cache_seed_dir = seed_dir
                return content
            except OSError as e:
                logger.warning(f"Failed to read TODO file {todo_path}: {e}")

        # 缓存空内容
        self._cache = ""
        self._cache_time = now
        self._cache_seed_dir = seed_dir
        return ""


def extract_critical_context(history: list[dict[str, Any]]) -> str | None:
    """提取关键上下文（从历史记录）

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