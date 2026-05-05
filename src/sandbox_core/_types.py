"""
Sandbox 类型定义

包含所有数据类型、枚举和权限类定义。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IsolationLevel(StrEnum):
    """隔离级别"""

    PROCESS = "process"  # 进程级隔离 (子进程执行)
    CONTAINER = "container"  # 容器级隔离 (Docker)
    VM = "vm"  # 虚拟机级隔离 (最强)


class PermissionAction(StrEnum):
    """权限动作"""

    ALLOW = "allow"
    DENY = "deny"
    READONLY = "readonly"


@dataclass
class SandboxPermission:
    """沙盒权限规则

    定义单个工具的执行权限：
    - action: 允许/拒绝/只读
    - path_patterns: 允许的路径模式列表
    - max_output_size: 最大输出大小限制
    """

    tool_name: str
    action: PermissionAction = PermissionAction.ALLOW
    path_patterns: list[str] | None = None
    max_output_size: int = 10000


@dataclass
class ExecutionResult:
    """工具执行结果"""

    tool_call_id: str
    content: str
    success: bool = True
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "tool_call_id": self.tool_call_id,
            "role": "tool",
            "content": self.content,
        }


# 默认工具名称列表
DEFAULT_TOOL_NAMES = [
    # 文件操作
    "file_read",
    "file_write",
    "file_edit",
    "list_directory",
    # 代码执行
    "run_shell_command",
    "code_as_policy",
    # 记忆操作
    "save_memory",
    "load_memory",
    "search_memory",
    # 用户交互
    "ask_user_question",
    # 技能操作
    "load_skill",
    # 子代理
    "spawn_subagent",
    "wait_for_subagent",
    "aggregate_subagent_results",
    "list_subagents",
    "kill_subagent",
    # Ralph Loop
    "start_ralph_loop",
    "check_ralph_status",
    "mark_ralph_complete",
    # Scheduler
    "create_scheduled_task",
    "remove_scheduled_task",
    "list_scheduled_tasks",
]


# 隔离级别描述
ISOLATION_LEVELS = {
    IsolationLevel.PROCESS: "进程级隔离 (子进程执行)",
    IsolationLevel.CONTAINER: "容器级隔离 (Docker)",
    IsolationLevel.VM: "虚拟机级隔离 (最强)",
}

# 路径相关参数名
PATH_KEYS = [
    "path",
    "file_path",
    "directory",
    "dir",
    "src",
    "dst",
    "source",
    "destination",
    "root",
    "base_path",
    "output_path",
]