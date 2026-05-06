"""
工具注册表核心实现

Wiki 知识落地特性:
- 工具分类 (ToolKind): 每个工具可指定类型
- 权限决策 (PermissionDecision): 基于分类的默认权限
- 并发安全判断: CONCURRENCY_SAFE_KINDS 判断是否可并发
- 可用性检查 (check_fn): 工具注册时检查 API Key 等要求
"""

import asyncio
from collections.abc import Callable
from typing import Any

from ._schema import infer_schema
from ._types import (
    CONCURRENCY_SAFE_KINDS,
    MUTATOR_KINDS,
    PermissionDecision,
    ToolKind,
)


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, dict] = {}
        self._tool_kinds: dict[str, ToolKind] = {}
        self._tool_permissions: dict[str, PermissionDecision] = {}
        self._tool_check_fns: dict[str, Callable[[], bool] | None] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any] | None = None,
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """注册工具

        Args:
            name: 工具名称
            func: 工具函数(可以是普通函数或异步函数)
            schema: 工具的 JSON Schema 描述(用于 function calling)
            kind: 工具分类 (Wiki 知识落地)
            permission: 权限决策 (Wiki 知识落地，默认基于 kind 自动推断)
            check_fn: 可用性检查函数 (Wiki 知识落地，检查 API Key 等要求)
        """
        self._tools[name] = func
        self._tool_schemas[name] = schema or infer_schema(func, name)

        # Wiki 知识落地: 工具分类和权限
        inferred_kind = kind or self._infer_kind_from_name(name)
        self._tool_kinds[name] = inferred_kind

        # 权限决策：如果未指定，基于分类自动推断
        if permission:
            self._tool_permissions[name] = permission
        else:
            self._tool_permissions[name] = self._infer_permission_from_kind(
                inferred_kind
            )

        # Wiki 知识落地: 可用性检查函数
        self._tool_check_fns[name] = check_fn

    def _infer_kind_from_name(self, name: str) -> ToolKind:
        """从工具名称推断分类"""
        name_lower = name.lower()
        if any(
            x in name_lower
            for x in ("read", "load", "get", "list", "search", "grep", "glob")
        ):
            return ToolKind.Read if "search" not in name_lower else ToolKind.Search
        if any(x in name_lower for x in ("write", "edit", "patch", "update", "save")):
            return ToolKind.Edit
        if any(x in name_lower for x in ("delete", "remove", "clear")):
            return ToolKind.Delete
        if any(x in name_lower for x in ("exec", "run", "code", "shell", "bash")):
            return ToolKind.Execute
        if any(x in name_lower for x in ("memory", "skill")):
            return ToolKind.Memory
        if any(x in name_lower for x in ("agent", "subagent", "spawn")):
            return ToolKind.Agent
        return ToolKind.Other

    def _infer_permission_from_kind(self, kind: ToolKind) -> PermissionDecision:
        """从分类推断权限决策"""
        if kind in CONCURRENCY_SAFE_KINDS:
            return PermissionDecision.Allow
        if kind == ToolKind.Agent:
            return PermissionDecision.Ask
        if kind in MUTATOR_KINDS:
            return PermissionDecision.Ask
        return PermissionDecision.Ask

    def get_kind(self, name: str) -> ToolKind:
        """获取工具分类"""
        return self._tool_kinds.get(name, ToolKind.Other)

    def get_permission(self, name: str) -> PermissionDecision:
        """获取工具权限决策"""
        return self._tool_permissions.get(name, PermissionDecision.Ask)

    def is_concurrency_safe(self, name: str) -> bool:
        """判断工具是否可安全并发执行"""
        return self.get_kind(name) in CONCURRENCY_SAFE_KINDS

    def is_mutator(self, name: str) -> bool:
        """判断工具是否具有副作用"""
        return self.get_kind(name) in MUTATOR_KINDS

    def is_available(self, name: str) -> bool:
        """判断工具是否可用"""
        check_fn = self._tool_check_fns.get(name)
        if check_fn is None:
            return True
        try:
            return check_fn()
        except Exception:
            return False

    def get_available_tools(self) -> list[str]:
        """获取所有可用的工具名称列表"""
        return [name for name in self._tools if self.is_available(name)]

    def get_unavailable_tools(self) -> list[tuple[str, str]]:
        """获取不可用的工具及其原因"""
        unavailable = []
        for name in self._tools:
            if not self.is_available(name):
                check_fn = self._tool_check_fns.get(name)
                if check_fn is None:
                    reason = "Unknown"
                else:
                    try:
                        check_fn()
                        reason = "Unknown"
                    except Exception as e:
                        reason = str(e)
                unavailable.append((name, reason))
        return unavailable

    def get_tool(self, name: str) -> Callable:
        """获取工具函数"""
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def get_schemas(self) -> list[dict]:
        """获取所有工具的 JSON Schema"""
        return list(self._tool_schemas.values())

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行工具(支持异步)"""
        func = self.get_tool(tool_name)
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)


__all__ = ["ToolRegistry"]