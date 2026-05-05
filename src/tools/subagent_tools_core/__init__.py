"""
Subagent 工具注册模块

提供工具注册函数：
- register_subagent_tools: 注册所有 Subagent 工具到 Registry

核心特性：
- 统一注册入口
- 同步和异步工具支持
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)

from ._async_tools import wait_for_subagent_async
from ._sync_tools import (
    aggregate_subagent_results,
    get_subagent_status,
    init_subagent_manager,
    kill_subagent,
    list_subagents,
    spawn_parallel_subagents,
    spawn_subagent,
    wait_for_subagent,
)


def register_subagent_tools(registry: "ToolRegistry") -> None:
    """注册 Subagent 工具到 Registry"""
    # 同步工具
    registry.register("spawn_subagent", spawn_subagent)
    registry.register("wait_for_subagent", wait_for_subagent)
    registry.register("aggregate_subagent_results", aggregate_subagent_results)
    registry.register("list_subagents", list_subagents)
    registry.register("kill_subagent", kill_subagent)
    registry.register("get_subagent_status", get_subagent_status)
    registry.register("spawn_parallel_subagents", spawn_parallel_subagents)

    # 异步工具
    registry.register("wait_for_subagent_async", wait_for_subagent_async)

    logger.info("Subagent tools registered: 8 tools")


__all__ = [
    "init_subagent_manager",
    "spawn_subagent",
    "wait_for_subagent",
    "wait_for_subagent_async",
    "aggregate_subagent_results",
    "list_subagents",
    "kill_subagent",
    "get_subagent_status",
    "spawn_parallel_subagents",
    "register_subagent_tools",
]