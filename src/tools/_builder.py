"""ToolRegistryBuilder - 流式 API 工具注册构建器

基于 DeepSeek-TUI 的 ToolRegistryBuilder 设计：
- 分类注册：按类别批量注册工具
- 流式 API：链式调用构建注册表
- 可选特性：按需启用/禁用工具类别

Wiki 知识落地 P6 (DeepSeek-TUI ToolRegistryBuilder)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ._builder_core import (
    with_builtin_tools,
    with_collaboration_tools,
    with_file_tools,
    with_shell_tools,
)
from ._builder_extra import (
    with_all_tools,
    with_memory_tools,
    with_ralph_tools,
    with_skill_tools,
    with_subagent_tools,
)
from ._registry import ToolRegistry
from ._types import PermissionDecision, ToolKind

if TYPE_CHECKING:
    from ._lazy_loading import ToolFactory

logger = logging.getLogger(__name__)


class ToolRegistryBuilder:
    """流式 API 工具注册构建器"""

    def __init__(self) -> None:
        self._tools: list[tuple[str, Callable, dict | None, ToolKind | None, PermissionDecision | None]] = []
        self._factories: list[tuple[str, "ToolFactory", ToolKind | None, PermissionDecision | None]] = []
        self._features: dict[str, bool] = {}

    def enable_feature(self, name: str, enabled: bool = True) -> "ToolRegistryBuilder":
        """启用功能标志"""
        self._features[name] = enabled
        return self

    def disable_feature(self, name: str) -> "ToolRegistryBuilder":
        """禁用功能标志"""
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
        """添加单个工具"""
        self._tools.append((name, func, schema, kind, permission))
        return self

    def add_factory(
        self,
        name: str,
        factory: "ToolFactory",
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
    ) -> "ToolRegistryBuilder":
        """添加延迟加载工厂"""
        self._factories.append((name, factory, kind, permission))
        return self

    # 分类注册方法委托给子模块
    def with_file_tools(self) -> "ToolRegistryBuilder":
        return with_file_tools(self)

    def with_shell_tools(self) -> "ToolRegistryBuilder":
        return with_shell_tools(self)

    def with_memory_tools(self) -> "ToolRegistryBuilder":
        return with_memory_tools(self)

    def with_subagent_tools(self, agent_registry: Any | None = None) -> "ToolRegistryBuilder":
        return with_subagent_tools(self, agent_registry)

    def with_skill_tools(self) -> "ToolRegistryBuilder":
        return with_skill_tools(self)

    def with_ralph_tools(self) -> "ToolRegistryBuilder":
        return with_ralph_tools(self)

    def with_collaboration_tools(self) -> "ToolRegistryBuilder":
        return with_collaboration_tools(self)

    def with_builtin_tools(self) -> "ToolRegistryBuilder":
        return with_builtin_tools(self)

    def with_all_tools(self) -> "ToolRegistryBuilder":
        return with_all_tools(self)

    def build(self) -> ToolRegistry:
        """构建最终的 ToolRegistry"""
        registry = ToolRegistry()

        for name, func, schema, kind, permission in self._tools:
            registry.register(name, func, schema=schema, kind=kind, permission=permission)

        for name, factory, kind, permission in self._factories:
            registry.register_factory(name, factory, kind=kind, permission=permission)

        logger.info(f"Built ToolRegistry with {len(self._tools)} tools, {len(self._factories)} factories")
        return registry


__all__ = ["ToolRegistryBuilder"]