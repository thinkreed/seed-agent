"""ToolRegistryBuilder - 流式 API 工具注册构建器

基于 DeepSeek-TUI 的 ToolRegistryBuilder 设计：
- 分类注册：按类别批量注册工具
- 流式 API：链式调用构建注册表
- 可选特性：按需启用/禁用工具类别
- 懒加载支持：与 ToolFactory 集成

使用示例:
    registry = ToolRegistryBuilder()
        .with_file_tools()
        .with_shell_tools()
        .with_search_tools()
        .with_memory_tools()
        .with_subagent_tools(agent_registry)
        .build()

设计模式:
- Builder Pattern: 分步构建复杂对象
- Fluent Interface: 链式方法调用
- Feature Flags: 条件启用工具类别
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ._registry import ToolRegistry
from ._types import ApprovalRequirement, PermissionDecision, ToolCapability, ToolKind

if TYPE_CHECKING:
    from ._lazy_loading import ToolFactory

logger = logging.getLogger(__name__)


class ToolRegistryBuilder:
    """流式 API 工具注册构建器

    基于 DeepSeek-TUI 的 ToolRegistryBuilder 设计：
    - 分类注册：按类别批量注册工具
    - 流式 API：链式调用构建注册表
    - 可选特性：按需启用/禁用工具类别
    - 懒加载支持：与 ToolFactory 集成

    Attributes:
        _tools: 待注册的工具列表
        _factories: 待注册的延迟加载工厂
        _features: 功能标志配置
    """

    def __init__(self) -> None:
        """初始化构建器"""
        self._tools: list[tuple[str, Callable, dict | None, ToolKind | None, PermissionDecision | None]] = []
        self._factories: list[tuple[str, "ToolFactory", ToolKind | None, PermissionDecision | None]] = []
        self._features: dict[str, bool] = {}

    def enable_feature(self, name: str, enabled: bool = True) -> "ToolRegistryBuilder":
        """启用功能标志

        Args:
            name: 功能名称
            enabled: 是否启用

        Returns:
            self: 支持链式调用
        """
        self._features[name] = enabled
        return self

    def disable_feature(self, name: str) -> "ToolRegistryBuilder":
        """禁用功能标志

        Args:
            name: 功能名称

        Returns:
            self: 支持链式调用
        """
        self._features[name] = False
        return self

    def add_tool(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any] | None = None,
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
    ) -> "ToolRegistryBuilder":
        """添加单个工具

        Args:
            name: 工具名称
            func: 工具函数
            schema: 工具 schema（可选）
            kind: 工具分类（可选）
            permission: 权限决策（可选）

        Returns:
            self: 支持链式调用
        """
        self._tools.append((name, func, schema, kind, permission))
        return self

    def add_factory(
        self,
        name: str,
        factory: "ToolFactory",
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
    ) -> "ToolRegistryBuilder":
        """添加延迟加载工厂

        Args:
            name: 工具名称
            factory: 工厂函数
            kind: 工具分类（可选）
            permission: 权限决策（可选）

        Returns:
            self: 支持链式调用
        """
        self._factories.append((name, factory, kind, permission))
        return self

    # === 分类注册方法 ===

    def with_file_tools(self) -> "ToolRegistryBuilder":
        """添加文件操作工具

        注册以下工具:
        - file_read: 文件读取
        - file_write: 文件写入
        - file_edit: 文件编辑

        Returns:
            self: 支持链式调用
        """
        from src.tools.builtin import file_edit, file_read, file_write

        self.add_tool("file_read", file_read, kind=ToolKind.Read, permission=PermissionDecision.Allow)
        self.add_tool("file_write", file_write, kind=ToolKind.Edit, permission=PermissionDecision.Ask)
        self.add_tool("file_edit", file_edit, kind=ToolKind.Edit, permission=PermissionDecision.Ask)
        return self

    def with_shell_tools(self) -> "ToolRegistryBuilder":
        """添加 Shell 执行工具

        注册以下工具:
        - code_as_policy: 代码执行

        Returns:
            self: 支持链式调用
        """
        from src.tools.builtin import code_as_policy

        self.add_tool(
            "code_as_policy",
            code_as_policy,
            kind=ToolKind.Execute,
            permission=PermissionDecision.Ask,
        )
        return self

    def with_memory_tools(self) -> "ToolRegistryBuilder":
        """添加记忆系统工具

        注册以下工具:
        - memory_write: 写入记忆
        - memory_read: 读取记忆
        - memory_list: 列出记忆

        Returns:
            self: 支持链式调用
        """
        # 检查记忆工具是否可用
        try:
            from src.tools.memory import memory_write

            self.add_tool(
                "memory_write",
                memory_write,
                kind=ToolKind.Memory,
                permission=PermissionDecision.Ask,
            )
        except ImportError:
            logger.debug("memory_write not available, skipping")

        try:
            from src.tools.memory import memory_read

            self.add_tool(
                "memory_read",
                memory_read,
                kind=ToolKind.Memory,
                permission=PermissionDecision.Allow,
            )
        except ImportError:
            logger.debug("memory_read not available, skipping")

        try:
            from src.tools.memory import memory_list

            self.add_tool(
                "memory_list",
                memory_list,
                kind=ToolKind.Read,
                permission=PermissionDecision.Allow,
            )
        except ImportError:
            logger.debug("memory_list not available, skipping")

        return self

    def with_subagent_tools(self, agent_registry: Any | None = None) -> "ToolRegistryBuilder":
        """添加子代理工具

        注册以下工具:
        - spawn_subagent: 创建子代理
        - task_stop: 停止任务

        Args:
            agent_registry: 代理注册表（可选）

        Returns:
            self: 支持链式调用
        """
        try:
            from src.tools.subagent_tools import spawn_subagent

            self.add_tool(
                "spawn_subagent",
                spawn_subagent,
                kind=ToolKind.Agent,
                permission=PermissionDecision.Ask,
            )
        except ImportError:
            logger.debug("spawn_subagent not available, skipping")

        try:
            from src.tools.task_stop import task_stop

            self.add_tool(
                "task_stop",
                task_stop,
                kind=ToolKind.Other,
                permission=PermissionDecision.Ask,
            )
        except ImportError:
            logger.debug("task_stop not available, skipping")

        return self

    def with_skill_tools(self) -> "ToolRegistryBuilder":
        """添加技能系统工具

        注册以下工具:
        - load_skill: 加载技能
        - list_skills: 列出技能

        Returns:
            self: 支持链式调用
        """
        try:
            from src.tools.skill_loader import load_skill

            self.add_tool(
                "load_skill",
                load_skill,
                kind=ToolKind.Read,
                permission=PermissionDecision.Allow,
            )
        except ImportError:
            logger.debug("load_skill not available, skipping")

        try:
            from src.tools.skill_loader import list_skills

            self.add_tool(
                "list_skills",
                list_skills,
                kind=ToolKind.Read,
                permission=PermissionDecision.Allow,
            )
        except ImportError:
            logger.debug("list_skills not available, skipping")

        return self

    def with_ralph_tools(self) -> "ToolRegistryBuilder":
        """添加 Ralph 循环工具

        注册以下工具:
        - ralph_start: 启动 Ralph 循环
        - ralph_stop: 停止 Ralph 循环

        Returns:
            self: 支持链式调用
        """
        try:
            from src.tools.ralph_tools import ralph_start

            self.add_tool(
                "ralph_start",
                ralph_start,
                kind=ToolKind.Other,
                permission=PermissionDecision.Ask,
            )
        except ImportError:
            logger.debug("ralph_start not available, skipping")

        try:
            from src.tools.ralph_tools import ralph_stop

            self.add_tool(
                "ralph_stop",
                ralph_stop,
                kind=ToolKind.Other,
                permission=PermissionDecision.Ask,
            )
        except ImportError:
            logger.debug("ralph_stop not available, skipping")

        return self

    def with_collaboration_tools(self) -> "ToolRegistryBuilder":
        """添加协作工具

        注册以下工具:
        - ask_user: 用户交互

        Returns:
            self: 支持链式调用
        """
        from src.tools.builtin import ask_user

        self.add_tool(
            "ask_user",
            ask_user,
            kind=ToolKind.Other,
            permission=PermissionDecision.Allow,
        )
        return self

    def with_builtin_tools(self) -> "ToolRegistryBuilder":
        """添加所有内置工具（便捷方法）

        等价于:
        - with_file_tools()
        - with_shell_tools()
        - with_collaboration_tools()

        Returns:
            self: 支持链式调用
        """
        return self.with_file_tools().with_shell_tools().with_collaboration_tools()

    def with_all_tools(self) -> "ToolRegistryBuilder":
        """添加所有可用工具（便捷方法）

        等价于:
        - with_builtin_tools()
        - with_memory_tools()
        - with_subagent_tools()
        - with_skill_tools()
        - with_ralph_tools()

        Returns:
            self: 支持链式调用
        """
        return (
            self.with_builtin_tools()
            .with_memory_tools()
            .with_subagent_tools()
            .with_skill_tools()
            .with_ralph_tools()
        )

    def build(self) -> ToolRegistry:
        """构建最终的 ToolRegistry

        将所有收集的工具和工厂注册到新的 ToolRegistry 中。

        Returns:
            ToolRegistry: 包含所有注册工具的注册表
        """
        registry = ToolRegistry()

        # 注册直接工具
        for name, func, schema, kind, permission in self._tools:
            registry.register(name, func, schema=schema, kind=kind, permission=permission)

        # 注册延迟加载工厂
        for name, factory, kind, permission in self._factories:
            registry.register_factory(name, factory, kind=kind, permission=permission)

        logger.info(f"Built ToolRegistry with {len(self._tools)} tools, {len(self._factories)} factories")
        return registry


__all__ = ["ToolRegistryBuilder"]