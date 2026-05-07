"""
SubagentManager - 兼容性入口

原 subagent_manager.py 已重构为 subagent_manager_core/ package。
此文件保持向后兼容，从 package 导入主类。

模块拆分:
- _task.py: 任务定义和辅助函数
- _manager.py: 管理器核心逻辑
- _orchestrator.py: RalphLoop 编排器

核心职责:
- 创建独立 SubagentInstance
- 并行执行调度
- 结果收集与过滤
- 超时管理
- 资源限制
"""

# 从 package 导入，保持向后兼容
from src.subagent_manager_core import (
    RalphSubagentOrchestrator,
    SubagentManager,
    SubagentTask,
    create_task,
    get_default_timeout,
)

__all__ = [
    "RalphSubagentOrchestrator",
    "SubagentManager",
    "SubagentTask",
    "create_task",
    "get_default_timeout",
]