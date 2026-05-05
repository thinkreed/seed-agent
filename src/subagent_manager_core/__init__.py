"""
SubagentManager - Package 入口

导出:
- SubagentManager: 管理器主类
- SubagentTask: 任务定义
- RalphSubagentOrchestrator: RalphLoop 编排器
- 辅助函数
"""

from src.subagent_manager_core._manager import SubagentManager
from src.subagent_manager_core._orchestrator import RalphSubagentOrchestrator
from src.subagent_manager_core._task import (
    SubagentTask,
    create_task,
    get_default_timeout,
)

__all__ = [
    "SubagentManager",
    "SubagentTask",
    "RalphSubagentOrchestrator",
    "create_task",
    "get_default_timeout",
]