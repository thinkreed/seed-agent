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
        """从函数签名推断 JSON Schema(简化版)"""
        sig = inspect.signature(func)
        params = sig.parameters
        
        properties = {}
        required = []
        
        for param_name, param in params.items():
            if param_name == "self" or param_name == "cls":
                continue
            
            param_type = "string" # 默认简化处理，实际可根据 type 映射
            if param.annotation is not inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object"
                }
                param_type = type_map.get(param.annotation, "string")
                
            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}"
            }
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
                
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": func.__doc__ or f"Execute {func.__name__}",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }