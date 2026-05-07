"""
Subagent 机制 - 独立上下文的子代理执行器

核心特性:
- 独立 context window，不共享主对话历史
- 可配置权限集（read-only, review, implement, plan）
- 并行执行支持
- 结果聚合（只返回关键结果，不污染主上下文）

OpenTelemetry 嵌入:
- Span: seed.subagent.execute
- Attributes: type, task_id, status

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容

模块结构:
- _subagent_types.py: 类型定义（枚举、状态、结果类）
- _subagent_config.py: 配置（权限集、系统提示、超时）
- _subagent_core.py: 核心类（SubagentInstance）
"""

# 从类型模块导入（向后兼容）
# 从配置模块导入（向后兼容）
from src._subagent_config import (
    DEFAULT_TIMEOUTS,
    MAX_SUBAGENT_ITERATIONS,
    PERMISSION_SETS,
    SUBAGENT_SYSTEM_PROMPTS,
    SUBAGENT_TYPE_PERMISSIONS,
)

# 从核心模块导入主类（向后兼容）
from src._subagent_core import SubagentInstance
from src._subagent_types import (
    SubagentResult,
    SubagentState,
    SubagentStatus,
    SubagentType,
    _get_subagent_type_key,
)

__all__ = [
    "DEFAULT_TIMEOUTS",
    "MAX_SUBAGENT_ITERATIONS",
    "PERMISSION_SETS",
    "SUBAGENT_SYSTEM_PROMPTS",
    "SUBAGENT_TYPE_PERMISSIONS",
    "SubagentInstance",
    "SubagentResult",
    "SubagentState",
    "SubagentStatus",
    "SubagentType",
    "_get_subagent_type_key",
]