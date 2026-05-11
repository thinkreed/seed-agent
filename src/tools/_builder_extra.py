"""ToolRegistryBuilder 扩展工具注册

扩展工具类别：
- with_memory_tools: 记忆系统工具
- with_subagent_tools: 子代理工具
- with_skill_tools: 技能系统工具
- with_ralph_tools: Ralph 循环工具
- with_all_tools: 所有工具便捷方法

Wiki 知识落地 P6 (DeepSeek-TUI ToolRegistryBuilder)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ._builder_core import with_builtin_tools
from ._types import PermissionDecision, ToolKind

if TYPE_CHECKING:
    from ._builder import ToolRegistryBuilder

logger = logging.getLogger(__name__)


def with_memory_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加记忆系统工具"""
    try:
        from src.tools.memory import memory_write

        builder.add_tool(
            "memory_write",
            memory_write,
            kind=ToolKind.Memory,
            permission=PermissionDecision.Ask,
        )
    except ImportError:
        logger.debug("memory_write not available, skipping")

    try:
        from src.tools.memory import memory_read

        builder.add_tool(
            "memory_read",
            memory_read,
            kind=ToolKind.Memory,
            permission=PermissionDecision.Allow,
        )
    except ImportError:
        logger.debug("memory_read not available, skipping")

    try:
        from src.tools.memory import memory_list

        builder.add_tool(
            "memory_list",
            memory_list,
            kind=ToolKind.Read,
            permission=PermissionDecision.Allow,
        )
    except ImportError:
        logger.debug("memory_list not available, skipping")

    return builder


def with_subagent_tools(builder: "ToolRegistryBuilder", agent_registry: Any | None = None) -> "ToolRegistryBuilder":
    """添加子代理工具"""
    try:
        from src.tools.subagent_tools import spawn_subagent

        builder.add_tool(
            "spawn_subagent",
            spawn_subagent,
            kind=ToolKind.Agent,
            permission=PermissionDecision.Ask,
        )
    except ImportError:
        logger.debug("spawn_subagent not available, skipping")

    try:
        from src.tools.task_stop import task_stop

        builder.add_tool(
            "task_stop",
            task_stop,
            kind=ToolKind.Other,
            permission=PermissionDecision.Ask,
        )
    except ImportError:
        logger.debug("task_stop not available, skipping")

    return builder


def with_skill_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加技能系统工具"""
    try:
        from src.tools.skill_loader import load_skill

        builder.add_tool(
            "load_skill",
            load_skill,
            kind=ToolKind.Read,
            permission=PermissionDecision.Allow,
        )
    except ImportError:
        logger.debug("load_skill not available, skipping")

    try:
        from src.tools.skill_loader import list_skills

        builder.add_tool(
            "list_skills",
            list_skills,
            kind=ToolKind.Read,
            permission=PermissionDecision.Allow,
        )
    except ImportError:
        logger.debug("list_skills not available, skipping")

    return builder


def with_ralph_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加 Ralph 循环工具"""
    try:
        from src.tools.ralph_tools import ralph_start

        builder.add_tool(
            "ralph_start",
            ralph_start,
            kind=ToolKind.Other,
            permission=PermissionDecision.Ask,
        )
    except ImportError:
        logger.debug("ralph_start not available, skipping")

    try:
        from src.tools.ralph_tools import ralph_stop

        builder.add_tool(
            "ralph_stop",
            ralph_stop,
            kind=ToolKind.Other,
            permission=PermissionDecision.Ask,
        )
    except ImportError:
        logger.debug("ralph_stop not available, skipping")

    return builder


def with_all_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加所有可用工具（便捷方法）"""
    return with_builtin_tools(
        with_memory_tools(with_subagent_tools(with_skill_tools(with_ralph_tools(builder))))
    )


__all__ = [
    "with_memory_tools",
    "with_subagent_tools",
    "with_skill_tools",
    "with_ralph_tools",
    "with_all_tools",
]