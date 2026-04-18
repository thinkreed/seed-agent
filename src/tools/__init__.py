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
    
    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行工具(支持异步)"""
        func = self.get_tool(tool_name)
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)
    
    def _infer_schema(self, func: Callable) -> Dict:
        """从函数签名推断 JSON Schema，支持嵌套类型(List, Dict)推断及更好的 Docstring 解析"""
        import typing
        import re
        import inspect

        sig = inspect.signature(func)
        params = sig.parameters
        
        # 解析 docstring 以获取参数描述 (支持 Args: 块格式)
        param_descriptions = {}
        if func.__doc__:
            # 逐行解析以兼容缩进不一致或混合格式
            skip_headers = {"args", "returns", "raises", "yields", "note", "example"}
            for line in func.__doc__.split('\n'):
                line = line.strip()
                if not line or line.endswith(':'):
                    continue
                match = re.match(r'([a-zA-Z_]\w*)\s*:\s*(.+)', line)
                if match:
                    name, desc = match.group(1), match.group(2).strip()
                    if name.lower() not in skip_headers:
                        param_descriptions[name] = desc

        properties = {}
        required = []
        
        def _resolve_type_to_schema(ann):
            """将 Python 类型转换为 JSON Schema 结构"""
            origin = typing.get_origin(ann)
            args = typing.get_args(ann)

            # 处理 List[T]
            if ann is list or origin is list:
                item_schema = {"type": "string"} # Default
                if args:
                    item_schema = _resolve_type_to_schema(args[0])
                return {"type": "array", "items": item_schema}
            
            # 处理 Dict
            if ann is dict or origin is dict:
                return {"type": "object"}

            # 处理 Union (包括 Optional[T] -> Union[T, None])
            if origin is typing.Union:
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    return _resolve_type_to_schema(non_none[0])
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

        for param_name, param in params.items():
            if param_name in ("self", "cls"):
                continue
            
            # 生成类型 schema
            param_schema = _resolve_type_to_schema(param.annotation)
            
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
                "name": func.__name__,
                "description": (func.__doc__ or f"Execute {func.__name__}").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }