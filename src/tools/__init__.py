import asyncio
import inspect
from typing import Dict, List, Callable, Any

class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: Dict[str, Dict] = {}
    
    def register(self, name: str, func: Callable, schema: Dict = None):
        """注册工具
        
        Args:
            name: 工具名称
            func: 工具函数(可以是普通函数或异步函数)
            schema: 工具的 JSON Schema 描述(用于 function calling)
        """
        self._tools[name] = func
        self._tool_schemas[name] = schema or self._infer_schema(func)
    
    def get_tool(self, name: str) -> Callable:
        """获取工具函数"""
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]
    
    def get_schemas(self) -> List[Dict]:
        """获取所有工具的 JSON Schema(用于 LLM 调用)"""
        return list(self._tool_schemas.values())
    
    async def execute(self, name: str, **kwargs) -> Any:
        """执行工具(支持异步)"""
        func = self.get_tool(name)
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)
    
    def _infer_schema(self, func: Callable) -> Dict:
        """从函数签名推断 JSON Schema，支持类型推断和 Docstring 解析"""
        import typing
        import re

        sig = inspect.signature(func)
        params = sig.parameters
        
        # 解析 docstring 以获取参数描述
        param_descriptions = {}
        if func.__doc__:
            # 简单匹配 "param_name: description" 格式
            matches = re.findall(r'\s+(\w+):\s+(.+?)(?=\n\s*\w+:|\Z)', func.__doc__, re.DOTALL)
            for p_name, p_desc in matches:
                param_descriptions[p_name] = p_desc.strip()

        properties = {}
        required = []
        
        def _resolve_type(ann):
            """将 Python 类型转换为 JSON Schema 类型字符串"""
            if ann is inspect.Parameter.empty:
                return "string"
            if ann is str: return "string"
            if ann is int: return "integer"
            if ann is float: return "number"
            if ann is bool: return "boolean"
            if ann is list or typing.get_origin(ann) is list:
                return "array"
            if ann is dict or typing.get_origin(ann) is dict:
                return "object"
            if typing.get_origin(ann) is typing.Union or typing.get_origin(ann) is typing.Optional:
                # 简单处理 Optional，取第一个非 None 参数
                args = typing.get_args(ann)
                for a in args:
                    if a is not type(None):
                        return _resolve_type(a)
            return "string"

        for param_name, param in params.items():
            if param_name == "self" or param_name == "cls":
                continue
            
            param_type = _resolve_type(param.annotation)
            description = param_descriptions.get(param_name, f"The {param_name} parameter")
                
            properties[param_name] = {
                "type": param_type,
                "description": description
            }
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
                
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": (func.__doc__ or f"Execute {func.__name__}").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }