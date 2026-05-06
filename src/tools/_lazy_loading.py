"""工具延迟加载机制 (Wiki 知识落地 - Qwen-Code P2)

基于 Qwen-Code ToolRegistry 设计:
- 按需加载工具，减少启动时开销
- 使用 inflight Map 防重复请求
- 预热机制批量加载所有延迟工具
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from ._schema import infer_schema

logger = logging.getLogger(__name__)

# 工厂函数类型：返回工具函数的异步函数
ToolFactory = Callable[[], Coroutine[None, None, Callable[..., Any]]]


async def ensure_tool_loaded(
    name: str,
    tools: dict[str, Callable],
    factories: dict[str, ToolFactory],
    inflight: dict[str, asyncio.Task],
    tool_schemas: dict[str, dict],
) -> Callable | None:
    """确保工具已加载 (防重复请求模式)

    Args:
        name: 工具名称
        tools: 已加载工具缓存
        factories: 延迟加载工厂
        inflight: 进行中的加载任务
        tool_schemas: 工具 schema 缓存

    Returns:
        工具函数，如果不存在则返回 None
    """
    # 1. 检查缓存
    cached = tools.get(name)
    if cached:
        factories.pop(name, None)
        return cached

    # 2. 检查是否有进行中的请求
    existing_task = inflight.get(name)
    if existing_task:
        logger.debug(f"Sharing inflight load for tool: {name}")
        return await existing_task

    # 3. 获取工厂函数
    factory = factories.get(name)
    if not factory:
        return None

    # 4. 创建加载任务
    async def _load() -> Callable:
        try:
            func = await factory()
            tools[name] = func
            if name not in tool_schemas:
                tool_schemas[name] = infer_schema(func, name)
            factories.pop(name, None)
            inflight.pop(name, None)
            logger.info(f"Lazy loaded tool: {name}")
            return func
        except Exception as e:
            inflight.pop(name, None)
            logger.error(f"Failed to load tool {name}: {e}")
            raise

    task = asyncio.create_task(_load())
    inflight[name] = task
    return await task


async def warm_all_tools(
    factories: dict[str, ToolFactory],
    tools: dict[str, Callable],
    inflight: dict[str, asyncio.Task],
    tool_schemas: dict[str, dict],
    strict: bool = False,
) -> None:
    """预热所有延迟加载的工具

    Args:
        factories: 延迟加载工厂
        tools: 已加载工具缓存
        inflight: 进行中的加载任务
        tool_schemas: 工具 schema 缓存
        strict: 如果为 True，加载失败会抛出异常
    """
    pending = list(factories.keys())
    if not pending:
        return

    logger.info(f"Warming {len(pending)} lazy tools...")

    async def _warm_single(name: str) -> None:
        try:
            await ensure_tool_loaded(name, tools, factories, inflight, tool_schemas)
        except Exception as e:
            if strict:
                raise
            logger.warning(f"Failed to warm tool {name}: {e}")

    await asyncio.gather(*[_warm_single(name) for name in pending])
    logger.info(f"Warmed {len(tools)} tools")


__all__ = ["ToolFactory", "ensure_tool_loaded", "warm_all_tools"]