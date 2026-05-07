"""
Subagent 工具集 - 为 AgentLoop 提供 Subagent 操作接口

模块拆分:
- subagent_tools_core/_sync_tools.py: 同步工具
- subagent_tools_core/_async_tools.py: 异步工具
- subagent_tools_core/__init__.py: 工具注册

核心工具:
- spawn_subagent: 创建并启动子代理
- wait_for_subagent: 等待子代理完成
- aggregate_subagent_results: 聚合多个子代理结果
- list_subagents: 列出所有子代理状态
- kill_subagent: 终止子代理

类型安全:
- 所有数值参数在入口处强制转换为整数
"""

# 导入拆分后的模块
from src.tools.subagent_tools_core import (
    aggregate_subagent_results,
    get_subagent_status,
    init_subagent_manager,
    kill_subagent,
    list_subagents,
    register_subagent_tools,
    spawn_parallel_subagents,
    spawn_subagent,
    wait_for_subagent,
    wait_for_subagent_async,
)

# 向后兼容: 导出 safe_int_convert (实际来自 utils.py)
from src.tools.utils import safe_int_convert as _safe_int_convert

__all__ = [
    "_safe_int_convert",
    "aggregate_subagent_results",
    "get_subagent_status",
    "init_subagent_manager",
    "kill_subagent",
    "list_subagents",
    "register_subagent_tools",
    "spawn_parallel_subagents",
    "spawn_subagent",
    "wait_for_subagent",
    "wait_for_subagent_async",
]