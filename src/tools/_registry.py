"""
工具注册表核心实现

Wiki 知识落地特性:
- 工具分类 (ToolKind): 每个工具可指定类型
- 权限决策 (PermissionDecision): 基于分类的默认权限
- 并发安全判断: CONCURRENCY_SAFE_KINDS 判断是否可并发
- 可用性检查 (check_fn): 工具注册时检查 API Key 等要求
- 延迟加载 (factories + inflight): 按需加载工具，防重复请求 (Qwen-Code P2)
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from ._schema import infer_schema
from ._types import (
    CONCURRENCY_SAFE_KINDS,
    MUTATOR_KINDS,
    PermissionDecision,
    ToolKind,
)

logger = logging.getLogger(__name__)

# 工厂函数类型：返回工具函数的异步函数
ToolFactory = Callable[[], Coroutine[None, None, Callable[..., Any]]]


class ToolRegistry:
    """工具注册表

    Wiki 知识落地 (Qwen-Code ToolRegistry 设计):
    - 延迟加载: 通过 register_factory 注册工厂函数，按需加载
    - 防重复请求: inflight Map 共享进行中的加载 Promise
    - 预热机制: warm_all 批量加载所有延迟工具
    """

    def __init__(self) -> None:
        # 已注册的工具
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, dict] = {}
        self._tool_kinds: dict[str, ToolKind] = {}
        self._tool_permissions: dict[str, PermissionDecision] = {}
        self._tool_check_fns: dict[str, Callable[[], bool] | None] = {}

        # Wiki 知识落地: 延迟加载机制 (Qwen-Code P2)
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

    # === Wiki 知识落地: 延迟加载机制 (Qwen-Code P2) ===

    def register_factory(
        self,
        name: str,
        factory: ToolFactory,
        kind: ToolKind | None = None,
        permission: PermissionDecision | None = None,
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """注册延迟加载工厂函数 (Wiki 知识落地)

        工具不会立即加载，而是在首次使用时通过 factory 函数加载。
        这可以减少启动时的加载开销。

        Args:
            name: 工具名称
            factory: 异步工厂函数，返回工具函数
            kind: 工具分类（可选，加载后设置）
            permission: 权限决策（可选，加载后设置）
            check_fn: 可用性检查函数（可选）

        Example:
            registry.register_factory(
                "vision_analyze",
                lambda: import_and_get("vision_tools", "analyze"),
                kind=ToolKind.Other,
            )
        """
        self._factories[name] = factory
        # 预设置分类和权限
        inferred_kind = kind or self._infer_kind_from_name(name)
        self._tool_kinds[name] = inferred_kind
        if permission:
            self._tool_permissions[name] = permission
        else:
            self._tool_permissions[name] = self._infer_permission_from_kind(
                inferred_kind
            )
        self._tool_check_fns[name] = check_fn
        logger.debug(f"Registered factory for tool: {name}")

    async def ensure_tool(self, name: str) -> Callable | None:
        """确保工具已加载 (Wiki 知识落地)

        使用防重复请求模式 (inflight Map)：
        - 如果已有缓存工具，直接返回
        - 如果已有进行中的加载，共享该 Task
        - 否则启动新的加载任务

        Args:
            name: 工具名称

        Returns:
            工具函数，如果不存在则返回 None
        """
        # 1. 检查缓存
        cached = self._tools.get(name)
        if cached:
            self._factories.pop(name, None)
            return cached

        # 2. 检查是否有进行中的请求
        existing_task = self._inflight.get(name)
        if existing_task:
            logger.debug(f"Sharing inflight load for tool: {name}")
            return await existing_task

        # 3. 获取工厂函数
        factory = self._factories.get(name)
        if not factory:
            return None

        # 4. 创建加载任务
        async def _load() -> Callable:
            try:
                func = await factory()
                self._tools[name] = func
                # 如果工厂没有提供 schema，则推断
                if name not in self._tool_schemas:
                    self._tool_schemas[name] = infer_schema(func, name)
                self._factories.pop(name, None)
                self._inflight.pop(name, None)
                logger.info(f"Lazy loaded tool: {name}")
                return func
            except Exception as e:
                self._inflight.pop(name, None)
                logger.error(f"Failed to load tool {name}: {e}")
                raise

        task = asyncio.create_task(_load())
        self._inflight[name] = task
        return await task

    async def warm_all(self, strict: bool = False) -> None:
        """预热所有延迟加载的工具 (Wiki 知识落地)

        批量加载所有通过 register_factory 注册的工具。

        Args:
            strict: 如果为 True，加载失败会抛出异常
                   如果为 False，失败只会记录警告
        """
        pending = list(self._factories.keys())
        if not pending:
            return

        logger.info(f"Warming {len(pending)} lazy tools...")

        async def _warm_single(name: str) -> None:
            try:
                await self.ensure_tool(name)
            except Exception as e:
                if strict:
                    raise
                logger.warning(f"Failed to warm tool {name}: {e}")

        await asyncio.gather(*[_warm_single(name) for name in pending])
        logger.info(f"Warmed {len(self._tools)} tools")

    def has_factory(self, name: str) -> bool:
        """检查是否有延迟加载工厂"""
        return name in self._factories

    def get_pending_factories(self) -> list[str]:
        """获取未加载的工厂名称列表"""
        return list(self._factories.keys())


__all__ = ["ToolRegistry", "ToolFactory"]