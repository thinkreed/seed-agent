"""
工具 Schema 推断模块

负责从函数签名推断 JSON Schema，用于 LLM function calling。
"""

import inspect
import re
import typing
from collections.abc import Callable
from typing import Any


def parse_docstring(doc: str | None) -> dict[str, str]:
    """解析 docstring 获取参数描述"""
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


def resolve_type_to_schema(ann: Any) -> dict[str, Any]:
    """将 Python 类型转换为 JSON Schema 结构"""
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)

    # 处理 list[T]
    if ann is list or origin is list:
        item_schema = {"type": "string"}  # Default
        if args:
            item_schema = resolve_type_to_schema(args[0])
        return {"type": "array", "items": item_schema}

    # 处理 Dict
    if ann is dict or origin is dict:
        return {"type": "object"}

    # 处理 Union (包括 Optional[T] -> Union[T, None])
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return resolve_type_to_schema(non_none[0])
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


def infer_schema(func: Callable, name: str | None = None) -> dict:
    """从函数签名推断 JSON Schema

    Args:
        func: 工具函数
        name: 工具名称（优先使用此名称而非 func.__name__）
    """
    tool_name = name or func.__name__
    sig = inspect.signature(func)
    params = sig.parameters

    # 解析 docstring
    param_descriptions = parse_docstring(func.__doc__)

    properties = {}
    required = []

    for param_name, param in params.items():
        if param_name in ("self", "cls"):
            continue

        # 生成类型 schema
        param_schema = resolve_type_to_schema(param.annotation)

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


__all__ = [
    "parse_docstring",
    "resolve_type_to_schema",
    "infer_schema",
]