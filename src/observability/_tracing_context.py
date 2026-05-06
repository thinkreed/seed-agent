"""
Tracing Context 传播模块

处理 asyncio context 的正确传播。
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from opentelemetry import context

T = TypeVar("T")


def create_task_with_context(
    coro: Coroutine[Any, Any, T],
    ctx: context.Context | None = None,
) -> asyncio.Task[T]:
    """创建继承 OTel context 的 asyncio task

    解决 asyncio.create_task() 默认不继承 context 的问题

    Args:
        coro: 协程对象
        ctx: Context (默认使用当前 context)

    Returns:
        asyncio.Task
    """
    if ctx is None:
        ctx = context.get_current()

    token = context.attach(ctx)
    try:
        return asyncio.create_task(coro)
    finally:
        context.detach(token)