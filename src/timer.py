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
    @timed("operation_name")
    async def my_function():
        # ... 执行操作 ...
"""

import logging
import time
from collections.abc import Callable, Coroutine
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger("seed_agent.timer")

P = ParamSpec("P")
R = TypeVar("R")


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


@contextmanager
def timed_context(name: str | None = None) -> "Timer":
    """计时上下文管理器

    Args:
        name: 计时器名称（用于日志）

    Yields:
        Timer: 计时器实例

    Example:
        with timed_context("api_call") as timer:
            # ... 执行操作 ...
        logger.info(f"{timer._name} took {timer.duration_ms:.2f}ms")
    """
    timer = Timer(name)
    timer.start()
    yield timer
    timer.stop()

    if name:
        logger.debug(f"{name} completed in {timer.duration_ms:.2f}ms")


def timed_async(name: str) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """异步函数计时装饰器

    Args:
        name: 操作名称（用于日志）

    Returns:
        装饰后的函数

    Example:
        @timed_async("llm_call")
        async def call_llm(prompt: str) -> dict:
            # ... 执行操作 ...
    """
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            timer = Timer(name)
            timer.start()
            try:
                result = await func(*args, **kwargs)
                timer.stop()
                logger.debug(f"{name} completed in {timer.duration_ms:.2f}ms")
                return result
            except Exception as e:
                timer.stop()
                logger.warning(f"{name} failed after {timer.duration_ms:.2f}ms: {type(e).__name__}")
                raise
        return wrapper
    return decorator


def timed_sync(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """同步函数计时装饰器

    Args:
        name: 操作名称（用于日志）

    Returns:
        装饰后的函数

    Example:
        @timed_sync("file_read")
        def read_file(path: str) -> str:
            # ... 执行操作 ...
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            timer = Timer(name)
            timer.start()
            try:
                result = func(*args, **kwargs)
                timer.stop()
                logger.debug(f"{name} completed in {timer.duration_ms:.2f}ms")
                return result
            except Exception as e:
                timer.stop()
                logger.warning(f"{name} failed after {timer.duration_ms:.2f}ms: {type(e).__name__}")
                raise
        return wrapper
    return decorator


# 简化函数：直接计算持续时间
def measure_duration(start_time: float) -> float:
    """计算持续时间（毫秒）

    Args:
        start_time: 开始时间（time.time() 返回值）

    Returns:
        float: 持续时间（毫秒）

    Example:
        start = time.time()
        # ... 执行操作 ...
        duration_ms = measure_duration(start)
    """
    return (time.time() - start_time) * 1000


def measure_duration_sec(start_time: float) -> float:
    """计算持续时间（秒）

    Args:
        start_time: 开始时间（time.time() 返回值）

    Returns:
        float: 持续时间（秒）
    """
    return time.time() - start_time