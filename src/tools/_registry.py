"""工具注册表核心实现

Wiki 知识落地特性:
- 工具分类 (ToolKind): 每个工具可指定类型
- 权限决策 (PermissionDecision): 基于分类的默认权限
- 并发安全判断: CONCURRENCY_SAFE_KINDS
- 可用性检查 (check_fn): 检查 API Key 等要求
- 延迟加载: 按需加载工具 (_lazy_loading.py)
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ._lazy_loading import ToolFactory, ensure_tool_loaded, warm_all_tools
from ._schema import infer_schema
from ._types import CONCURRENCY_SAFE_KINDS, MUTATOR_KINDS, PermissionDecision, ToolKind

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表

    Wiki 知识落地 (Qwen-Code ToolRegistry 设计):
    - 延迟加载: 通过 register_factory 注册工厂函数
    - 防重复请求: inflight Map 共享进行中的加载 Promise
    - 预热机制: warm_all 批量加载所有延迟工具
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, dict] = {}
        self._tool_kinds: dict[str, ToolKind] = {}
        self._tool_permissions: dict[str, PermissionDecision] = {}
        self._tool_check_fns: dict[str, Callable[[], bool] | None] = {}
        self._factories: dict[str, ToolFactory] = {}
        self._inflight: dict[str, asyncio.Task] = {}

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        schema: dict[str, Any] | None = None,
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """注册工具"""
        self._tools[name] = func
        self._tool_schemas[name] = schema or infer_schema(func, name)
        inferred_kind = kind or self._infer_kind_from_name(name)
        self._tool_kinds[name] = inferred_kind
        self._tool_permissions[name] = permission or self._infer_permission_from_kind(inferred_kind)
        self._tool_check_fns[name] = check_fn

    def _infer_kind_from_name(self, name: str) -> ToolKind:
        """从工具名称推断分类"""
        name_lower = name.lower()
        if any(x in name_lower for x in ("read", "load", "get", "list", "grep", "glob")):
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
        return self._tool_kinds.get(name, ToolKind.Other)

    def get_permission(self, name: str) -> PermissionDecision:
        return self._tool_permissions.get(name, PermissionDecision.Ask)

    def is_concurrency_safe(self, name: str) -> bool:
        return self.get_kind(name) in CONCURRENCY_SAFE_KINDS

    def is_mutator(self, name: str) -> bool:
        return self.get_kind(name) in MUTATOR_KINDS

    def is_available(self, name: str) -> bool:
        check_fn = self._tool_check_fns.get(name)
        if check_fn is None:
            return True
        try:
            return check_fn()
        except Exception:
            return False

    def get_available_tools(self) -> list[str]:
        return [name for name in self._tools if self.is_available(name)]

    def get_tool(self, name: str) -> Callable:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def get_schemas(self) -> list[dict]:
        return list(self._tool_schemas.values())

    async def execute(self, tool_name: str, **kwargs) -> Any:
        func = self.get_tool(tool_name)
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)

    # === 延迟加载 (Wiki 知识落地 P2) ===

    def register_factory(
        self,
        name: str,
        factory: ToolFactory,
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """注册延迟加载工厂函数"""
        self._factories[name] = factory
        inferred_kind = kind or self._infer_kind_from_name(name)
        self._tool_kinds[name] = inferred_kind
        self._tool_permissions[name] = permission or self._infer_permission_from_kind(inferred_kind)
        self._tool_check_fns[name] = check_fn
        logger.debug(f"Registered factory for tool: {name}")

    async def ensure_tool(self, name: str) -> Callable | None:
        """确保工具已加载"""
        return await ensure_tool_loaded(
            name, self._tools, self._factories, self._inflight, self._tool_schemas
        )

    async def warm_all(self, strict: bool = False) -> None:
        """预热所有延迟加载的工具"""
        await warm_all_tools(
            self._factories, self._tools, self._inflight, self._tool_schemas, strict
        )

    def has_factory(self, name: str) -> bool:
        return name in self._factories

    def get_pending_factories(self) -> list[str]:
        return list(self._factories.keys())


__all__ = ["ToolFactory", "ToolRegistry"]