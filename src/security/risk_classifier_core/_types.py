"""
命令风险分类器 - 类型定义和配置

包含:
- RiskLevel 枚举
- RiskAction 枚举
- RiskLevelConfig 配置
- ClassificationResult 结果
- 风险配置表
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """风险等级"""

    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"


class RiskAction(StrEnum):
    """风险处理策略"""

    AUTO_EXECUTE = "auto_execute"
    LOG_AND_EXECUTE = "log_and_execute"
    REQUEST_CONFIRM = "request_confirm"
    BLOCK = "block"


@dataclass
class RiskLevelConfig:
    """风险等级配置"""

    action: RiskAction
    description: str
    log_level: str
    require_user_approval: bool = False
    block_message: str = ""


# 风险等级配置表
RISK_LEVEL_CONFIGS: dict[RiskLevel, RiskLevelConfig] = {
    RiskLevel.SAFE: RiskLevelConfig(
        action=RiskAction.AUTO_EXECUTE,
        description="无风险操作，自动执行",
        log_level="INFO",
    ),
    RiskLevel.CAUTION: RiskLevelConfig(
        action=RiskAction.LOG_AND_EXECUTE,
        description="轻微风险，记录后执行",
        log_level="WARNING",
    ),
    RiskLevel.RISKY: RiskLevelConfig(
        action=RiskAction.REQUEST_CONFIRM,
        description="有风险，请求用户确认",
        log_level="WARNING",
        require_user_approval=True,
    ),
    RiskLevel.DANGEROUS: RiskLevelConfig(
        action=RiskAction.BLOCK,
        description="危险操作，直接拦截",
        log_level="ERROR",
        block_message="此操作被系统安全策略拦截",
    ),
}


@dataclass
class ClassificationResult:
    """分类结果"""

    risk_level: RiskLevel
    action: RiskAction
    score: float
    tool_name: str
    args: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    factors: list[str] = field(default_factory=list)


# 工具基础风险表
TOOL_BASE_RISKS: dict[str, float] = {
    # 低风险工具（只读）
    "file_read": 0.0,
    "list_directory": 0.0,
    "ask_user": 0.0,
    "search_history": 0.0,
    "read_memory_index": 0.0,
    "search_memory": 0.0,
    "load_skill": 0.0,
    "git_status": 0.0,
    "git_diff": 0.0,
    "list_subagents": 0.0,
    "check_ralph_status": 0.0,
    "list_scheduled_tasks": 0.0,
    # 中风险工具（写入/执行）
    "file_write": 0.4,
    "file_edit": 0.4,
    "write_memory": 0.3,
    "create_directory": 0.3,
    "run_python_script": 0.4,
    "run_test": 0.3,
    "git_commit": 0.4,
    "spawn_subagent": 0.4,
    "wait_for_subagent": 0.2,
    "aggregate_subagent_results": 0.2,
    "create_scheduled_task": 0.4,
    # 高风险工具（系统操作）
    "code_as_policy": 0.8,
    "run_shell_command": 0.8,
    "delete_file": 0.7,
    "install_package": 0.6,
    "git_push": 0.9,
    "kill_subagent": 0.5,
    "remove_scheduled_task": 0.5,
    # 默认中等风险
    "default": 0.5,
}

# 用户权限等级修正
USER_LEVEL_MODIFIERS: dict[str, float] = {
    "admin": -0.4,
    "trusted": -0.2,
    "normal": 0.0,
    "guest": 0.3,
    "restricted": 0.5,
}

# Sandbox 隔离等级修正
ISOLATION_LEVEL_MODIFIERS: dict[str, float] = {
    "vm": -0.8,
    "container": -0.5,
    "process": -0.2,
    "none": 0.0,
}