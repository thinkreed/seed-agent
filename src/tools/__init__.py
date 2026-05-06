"""
工具系统模块

负责:
1. 工具注册与发现 (ToolRegistry、动态加载)
2. 工具调用验证 (参数检查、权限控制、路径安全)
3. 工具并发执行 (asyncio.gather、路径重叠防护)
4. 工具结果处理 (输出截断、错误格式化)

核心组件:
- ToolRegistry: 全局工具注册表
- builtin_tools: 内置工具实现
- memory_tools: 记忆系统工具
- skill_loader: 技能加载器
- session_db: 会话数据库

Wiki 知识落地 (基于 Qwen-Code 工具系统设计):
- ToolKind: 工具分类枚举 (Read/Edit/Delete/Execute/Search 等)
- PermissionDecision: 权限三级模式 (allow/ask/deny)
- MUTATOR_KINDS: 具有副作用的工具类型
- CONCURRENCY_SAFE_KINDS: 可安全并发执行的工具类型

版本: v2.1 (Wiki 知识落地版)
"""

import asyncio
import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any


# === Wiki 知识落地: 工具分类系统 (基于 Qwen-Code) ===


class ToolKind(Enum):
    """工具分类枚举

    基于 Qwen-Code 的 Kind 设计，将工具按操作类型分类：
    - Read: 只读操作（文件读取、搜索）
    - Edit: 编辑操作（文件修改）
    - Delete: 删除操作（文件删除）
    - Execute: 执行操作（代码执行、Shell 命令）
    - Search: 搜索操作（grep、glob）
    - Memory: 记忆操作（读写记忆）
    - Agent: 子代理操作（spawn subagent）
    - Other: 其他操作

    用途：
    - 权限检查：不同类型有不同的默认权限
    - 并发控制：判断是否可以并发执行
    - 副作用检测：判断是否需要用户确认
    """

    Read = "read"
    Edit = "edit"
    Delete = "delete"
    Execute = "execute"
    Search = "search"
    Memory = "memory"
    Agent = "agent"
    Other = "other"


class PermissionDecision(Enum):
    """权限决策枚举

    基于 Qwen-Code 的三级权限模式：
    - allow: 固有安全，直接执行无需确认
    - ask: 需要用户确认后执行
    - deny: 安全违规，拒绝执行

    用途：
    - 工具调用前的权限检查
    - 用户确认流程的决策
    - 安全策略的实现
    """

    Allow = "allow"
    Ask = "ask"
    Deny = "deny"


# 具有副作用的工具类型（需要用户确认）
MUTATOR_KINDS: list[ToolKind] = [
    ToolKind.Edit,
    ToolKind.Delete,
    ToolKind.Execute,
    ToolKind.Memory,
]

# 可安全并发执行的工具类型（纯读取，无写入）
CONCURRENCY_SAFE_KINDS: set[ToolKind] = {
    ToolKind.Read,
    ToolKind.Search,
}


class ToolRegistry:
    """工具注册表

    Wiki 知识落地特性:
    - 工具分类 (ToolKind): 每个工具可指定类型
    - 权限决策 (PermissionDecision): 基于分类的默认权限
    - 并发安全判断: CONCURRENCY_SAFE_KINDS 判断是否可并发
    - 可用性检查 (check_fn): 工具注册时检查 API Key 等要求
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, dict] = {}
        self._tool_kinds: dict[str, ToolKind] = {}  # Wiki: 工具分类
        self._tool_permissions: dict[str, PermissionDecision] = {}  # Wiki: 权限决策
        self._tool_check_fns: dict[str, Callable[[], bool] | None] = {}  # Wiki: 可用性检查

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
        self._tool_schemas[name] = schema or self._infer_schema(func, name)

        # Wiki 知识落地: 工具分类和权限
        inferred_kind = kind or self._infer_kind_from_name(name)
        self._tool_kinds[name] = inferred_kind

        # 权限决策：如果未指定，基于分类自动推断
        if permission:
            self._tool_permissions[name] = permission
        else:
            self._tool_permissions[name] = self._infer_permission_from_kind(inferred_kind)

        # Wiki 知识落地: 可用性检查函数
        self._tool_check_fns[name] = check_fn

    def _infer_kind_from_name(self, name: str) -> ToolKind:
        """从工具名称推断分类"""
        name_lower = name.lower()
        if any(x in name_lower for x in ("read", "load", "get", "list", "search", "grep", "glob")):
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
        # 只读和搜索工具默认允许
        if kind in CONCURRENCY_SAFE_KINDS:
            return PermissionDecision.Allow
        # 子代理操作默认需要确认
        if kind == ToolKind.Agent:
            return PermissionDecision.Ask
        # 其他修改操作需要确认
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
        """判断工具是否可用 (Wiki 知识落地)

        检查工具是否满足执行条件：
        - 无 check_fn: 默认可用
        - 有 check_fn: 执行检查函数

        Args:
            name: 工具名称

        Returns:
            True 如果工具可用
        """
        check_fn = self._tool_check_fns.get(name)
        if check_fn is None:
            return True
        try:
            return check_fn()
        except Exception:
            return False

    def get_available_tools(self) -> list[str]:
        """获取所有可用的工具名称列表 (Wiki 知识落地)

        Returns:
            所有 is_available() 返回 True 的工具名称
        """
        return [name for name in self._tools if self.is_available(name)]

    def get_unavailable_tools(self) -> list[tuple[str, str]]:
        """获取不可用的工具及其原因 (Wiki 知识落地)

        Returns:
            (tool_name, reason) 列表
        """
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
        """获取所有工具的 JSON Schema(用于 LLM 调用)"""
        return list(self._tool_schemas.values())

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行工具(支持异步)"""
        func = self.get_tool(tool_name)
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)

    @staticmethod
    def _parse_docstring(doc: str | None) -> dict[str, str]:
        """解析 docstring 获取参数描述"""
        import re

        param_descriptions: dict[str, str] = {}
        if not doc:
            return param_descriptions

        skip_headers: set[str] = {
            "args",
            "returns",
            "raises",
            "yields",
            "note",
            "example",
        }
        for line in doc.split("\n"):
            line = line.strip()
            if not line or line.endswith(":"):
                continue
            match = re.match(r"([a-zA-Z_]\w*)\s*:\s*(.+)", line)
            if match:
                name, desc = match.group(1), match.group(2).strip()
                if name.lower() not in skip_headers:
                    param_descriptions[name] = desc
        return param_descriptions

    @staticmethod
    def _resolve_type_to_schema(ann: Any) -> dict[str, Any]:
        """将 Python 类型转换为 JSON Schema 结构"""
        import typing

        origin = typing.get_origin(ann)
        args = typing.get_args(ann)

        # 处理 list[T]
        if ann is list or origin is list:
            item_schema = {"type": "string"}  # Default
            if args:
                item_schema = ToolRegistry._resolve_type_to_schema(args[0])
            return {"type": "array", "items": item_schema}

        # 处理 Dict
        if ann is dict or origin is dict:
            return {"type": "object"}

        # 处理 Union (包括 Optional[T] -> Union[T, None])
        if origin is typing.Union:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return ToolRegistry._resolve_type_to_schema(non_none[0])
            # 复杂 Union 默认返回 string
            return {"type": "string"}

        # 基础类型
        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
        }
        return type_map.get(ann, {"type": "string"})

    def _infer_schema(self, func: Callable, name: str | None = None) -> dict:
        """从函数签名推断 JSON Schema

        Args:
            func: 工具函数
            name: 工具名称（优先使用此名称而非 func.__name__）
        """
        tool_name = name or func.__name__
        sig = inspect.signature(func)
        params = sig.parameters

        # 解析 docstring
        param_descriptions = self._parse_docstring(func.__doc__)

        properties = {}
        required = []

        for param_name, param in params.items():
            if param_name in ("self", "cls"):
                continue

            # 生成类型 schema
            param_schema = self._resolve_type_to_schema(param.annotation)

            # 添加描述
            description = param_descriptions.get(param_name, "")
            if not description:
                description = f"The {param_name} parameter"
            param_schema["description"] = description

            properties[param_name] = param_schema

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": (func.__doc__ or f"Execute {tool_name}").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# === 导出 ===

__all__ = [
    # 工具分类系统 (Wiki 知识落地)
    "ToolKind",
    "PermissionDecision",
    "MUTATOR_KINDS",
    "CONCURRENCY_SAFE_KINDS",
    # 核心类
    "ToolRegistry",
]
