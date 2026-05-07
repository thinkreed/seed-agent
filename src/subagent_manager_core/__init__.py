"""
SubagentManager - Package 入口

导出:
- SubagentManager: 管理器主类
- SubagentTask: 任务定义
- RalphSubagentOrchestrator: RalphLoop 编排器
- 辅助函数

Wiki 知识落地 P3 (基于 ai-hedge-fund Agent 系统设计):
- AgentConfig: Agent 元数据配置
- AgentSignal: 统一信号输出格式
- AGENT_CONFIG: Agent 注册表
- get_agent_nodes/get_agents_list: 注册发现函数
- resolve_agent_execution_order: 依赖图拓扑排序
"""

from src.subagent_manager_core._agent_registry import (
    AGENT_CONFIG,
    AgentConfig,
    AgentSignal,
    AgentSignalType,
    get_agent_by_type,
    get_agent_dependencies,
    get_agent_nodes,
    get_agents_list,
    resolve_agent_execution_order,
)
from src.subagent_manager_core._manager import SubagentManager
from src.subagent_manager_core._orchestrator import RalphSubagentOrchestrator
from src.subagent_manager_core._task import (
    SubagentTask,
    create_task,
    get_default_timeout,
)

__all__ = [
    "AGENT_CONFIG",
    # Wiki 知识落地 P3 (ai-hedge-fund Agent 系统)
    "AgentConfig",
    "AgentSignal",
    "AgentSignalType",
    "RalphSubagentOrchestrator",
    # 核心类
    "SubagentManager",
    "SubagentTask",
    # 辅助函数
    "create_task",
    "get_agent_by_type",
    "get_agent_dependencies",
    "get_agent_nodes",
    "get_agents_list",
    "get_default_timeout",
    "resolve_agent_execution_order",
]