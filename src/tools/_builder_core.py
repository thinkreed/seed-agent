"""ToolRegistryBuilder 核心工具注册

核心工具类别：
- with_file_tools: 文件操作工具
- with_shell_tools: Shell 执行工具
- with_collaboration_tools: 协作工具
- with_builtin_tools: 内置工具便捷方法

Wiki 知识落地 P6 (DeepSeek-TUI ToolRegistryBuilder)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._types import PermissionDecision, ToolKind

if TYPE_CHECKING:
    from ._builder import ToolRegistryBuilder

logger = logging.getLogger(__name__)


def with_file_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加文件操作工具"""
    from src.tools.builtin import file_edit, file_read, file_write

    builder.add_tool("file_read", file_read, kind=ToolKind.Read, permission=PermissionDecision.Allow)
    builder.add_tool("file_write", file_write, kind=ToolKind.Edit, permission=PermissionDecision.Ask)
    builder.add_tool("file_edit", file_edit, kind=ToolKind.Edit, permission=PermissionDecision.Ask)
    return builder


def with_shell_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加 Shell 执行工具"""
    from src.tools.builtin import code_as_policy

    builder.add_tool(
        "code_as_policy",
        code_as_policy,
        kind=ToolKind.Execute,
        permission=PermissionDecision.Ask,
    )
    return builder


def with_collaboration_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加协作工具"""
    from src.tools.builtin import ask_user

    builder.add_tool(
        "ask_user",
        ask_user,
        kind=ToolKind.Other,
        permission=PermissionDecision.Allow,
    )
    return builder


def with_builtin_tools(builder: "ToolRegistryBuilder") -> "ToolRegistryBuilder":
    """添加所有内置工具（便捷方法）"""
    return with_file_tools(with_shell_tools(with_collaboration_tools(builder)))


__all__ = ["with_file_tools", "with_shell_tools", "with_collaboration_tools", "with_builtin_tools"]