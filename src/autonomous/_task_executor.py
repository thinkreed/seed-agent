"""任务执行模块

提供自主探索任务执行功能:
- execute_autonomous_task: 执行自主探索任务
- run_ralph_loop: Ralph Loop 主循环
- handle_response: 处理响应
- notify_completion: 通知探索完成

从 AutonomousExplorer 中提取，保持接口不变。

此模块作为 facade，从子模块导入所有功能以保持向后兼容。
"""

# 从子模块导入所有功能
from src.autonomous._executor_constants import (
    COMPLETION_MARKERS,
    CONTEXT_RESET_ENABLED,
    CONTEXT_RESET_INTERVAL,
    RALPH_MAX_DURATION,
    RALPH_MAX_ITERATIONS,
)
from src.autonomous._executor_core import TaskExecutor

__all__ = [
    "TaskExecutor",
    "CONTEXT_RESET_ENABLED",
    "CONTEXT_RESET_INTERVAL",
    "RALPH_MAX_ITERATIONS",
    "RALPH_MAX_DURATION",
    "COMPLETION_MARKERS",
]