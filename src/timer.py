"""Timer 辅助模块

提供简洁的计时功能，减少重复的时间计算代码。

使用方式:
    # 1. 手动计时
    timer = Timer()
    timer.start()
    # ... 执行操作 ...
    duration_ms = timer.stop()

    # 2. 上下文管理器
    with Timer() as timer:
        # ... 执行操作 ...
        duration_ms = timer.duration_ms

    # 3. 装饰器（用于函数计时）
    @timed_sync("operation_name")
    def my_function():
        # ... 执行操作 ...
"""

import logging
import time
from typing import Any

logger = logging.getLogger("seed_agent.timer")


class Timer:
    """简洁的计时器类

    特性:
    - 支持手动 start/stop
    - 支持上下文管理器 (with Timer())
    - 自动计算毫秒和秒
    - 支持多次 start/stop（累积计时）
    """

    def __init__(self, name: str | None = None):
        """初始化计时器

        Args:
            name: 计时器名称（用于日志）
        """
        self._name = name
        self._start_time: float | None = None
        self._total_duration: float = 0.0
        self._running: bool = False
        self._duration_ms: float = 0.0

    def start(self) -> "Timer":
        """开始计时

        Returns:
            self，支持链式调用

        Raises:
            RuntimeError: 计时器已在运行
        """
        if self._running:
            raise RuntimeError(f"Timer '{self._name}' is already running")

        self._start_time = time.time()
        self._running = True
        return self

    def stop(self) -> float:
        """停止计时并返回持续时间（毫秒）

        Returns:
            float: 持续时间（毫秒）

        Raises:
            RuntimeError: 计时器未在运行
        """
        if not self._running:
            raise RuntimeError(f"Timer '{self._name}' is not running")

        # 类型断言：当 _running 为 True 时，_start_time 必定已设置
        assert self._start_time is not None
        duration = (time.time() - self._start_time) * 1000
        self._total_duration += duration
        self._duration_ms = duration
        self._running = False
        self._start_time = None

        return duration

    def reset(self) -> "Timer":
        """重置计时器

        Returns:
            self，支持链式调用
        """
        self._start_time = None
        self._total_duration = 0.0
        self._running = False
        self._duration_ms = 0.0
        return self

    @property
    def duration_ms(self) -> float:
        """获取最近一次计时的持续时间（毫秒）"""
        return self._duration_ms

    @property
    def duration_sec(self) -> float:
        """获取最近一次计时的持续时间（秒）"""
        return self._duration_ms / 1000

    @property
    def total_duration_ms(self) -> float:
        """获取累积持续时间（毫秒）"""
        return self._total_duration

    @property
    def is_running(self) -> bool:
        """检查计时器是否在运行"""
        return self._running

    def __enter__(self) -> "Timer":
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器退出"""
        if self._running:
            self.stop()


# 从子模块导入并导出公共 API
from src._timer_decorators import timed_async, timed_context, timed_sync
from src._timer_utils import measure_duration, measure_duration_sec

__all__ = [
    "Timer",
    "timed_context",
    "timed_async",
    "timed_sync",
    "measure_duration",
    "measure_duration_sec",
]