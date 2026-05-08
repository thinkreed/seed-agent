"""Timer 装饰器和上下文管理器模块

提供函数计时装饰器和上下文管理器。
"""

import logging
from collections.abc import Callable, Coroutine, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger("seed_agent.timer")

P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def timed_context(name: str | None = None) -> Generator[Any, None, None]:
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
    from src.timer import Timer

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
    from src.timer import Timer

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
    from src.timer import Timer

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