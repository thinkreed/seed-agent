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
"""

import asyncio
import inspect
from typing import Any, Callable


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._tool_schemas: dict[str, dict] = {}

    def register(
        self, name: str, func: Callable[..., Any], schema: dict[str, Any] | None = None
    ) -> None:
        """注册工具

        Args:
            name: 工具名称
            func: 工具函数(可以是普通函数或异步函数)
            schema: 工具的 JSON Schema 描述(用于 function calling)
        """
        self._tools[name] = func
        self._tool_schemas[name] = schema or self._infer_schema(func, name)

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
