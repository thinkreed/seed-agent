"""
AgentConfig 注册机制

基于 ai-hedge-fund ANALYST_CONFIG 设计，提供 Agent 元数据注册和发现功能。
Wiki 知识落地 P3 (基于 ai-hedge-fund Agent 系统设计)
"""

from typing import Any

from src._subagent_types import SubagentType
from src.subagent_manager_core._agent_types import AgentConfig, AgentSignal, AgentSignalType

# === Agent 注册表 ===

AGENT_CONFIG: dict[str, AgentConfig] = {
    "explore": AgentConfig(
        display_name="Explorer",
        description="只读探索 Agent",
        style="搜索文件、阅读代码、分析结构，不做任何修改",
        capabilities=["read_only", "search", "analyze"],
        subagent_type=SubagentType.EXPLORE,
        order=1,
        prerequisites=[],
    ),
    "review": AgentConfig(
        display_name="Reviewer",
        description="审查验证 Agent",
        style="验证实现质量、运行测试、检查安全，可执行代码",
        capabilities=["read_only", "execute", "test", "security_check"],
        subagent_type=SubagentType.REVIEW,
        order=2,
        prerequisites=["explore"],
    ),
    "implement": AgentConfig(
        display_name="Implementer",
        description="实现执行 Agent",
        style="编写代码、修改文件、解决问题，全权限执行",
        capabilities=["write", "execute", "modify", "create"],
        subagent_type=SubagentType.IMPLEMENT,
        order=3,
        prerequisites=["explore", "review"],
    ),
    "plan": AgentConfig(
        display_name="Planner",
        description="规划分析 Agent",
        style="制定执行计划、分析架构、沉淀经验，只读 + 记忆写入",
        capabilities=["read_only", "plan", "memory_write", "analyze"],
        subagent_type=SubagentType.PLAN,
        order=4,
        prerequisites=["explore"],
    ),
}


def get_agent_nodes() -> dict[str, tuple[str, AgentConfig]]:
    """获取 Agent 名称到 (类型键, 配置) 的映射"""
    return {key: (f"{key}_agent", config) for key, config in AGENT_CONFIG.items()}


def get_agents_list() -> list[dict[str, Any]]:
    """获取 Agent 列表用于 API 响应，按 order 排序"""
    return [config.to_dict() for _, config in sorted(AGENT_CONFIG.items(), key=lambda x: x[1].order)]


def get_agent_by_type(subagent_type: SubagentType) -> AgentConfig | None:
    """根据 SubagentType 获取 Agent 配置"""
    for config in AGENT_CONFIG.values():
        if config.subagent_type == subagent_type:
            return config
    return None


def get_agent_dependencies(agent_key: str) -> list[str]:
    """获取 Agent 的前置依赖列表（基于 Shannon 依赖图设计）"""
    config = AGENT_CONFIG.get(agent_key)
    return config.prerequisites if config else []


def resolve_agent_execution_order(agent_keys: list[str]) -> list[str]:
    """解析 Agent 执行顺序（基于依赖图拓扑排序）

    Args:
        agent_keys: 需要执行的 Agent 键名列表

    Returns:
        按依赖顺序排列的 Agent 键名列表
    """
    visited: set[str] = set()
    result: list[str] = []

    def visit(key: str) -> None:
        if key in visited:
            return
        visited.add(key)
        for prereq in get_agent_dependencies(key):
            if prereq in agent_keys:
                visit(prereq)
        result.append(key)

    for key in agent_keys:
        visit(key)

    return result


__all__ = [
    "AGENT_CONFIG",
    "AgentConfig",
    "AgentSignal",
    "AgentSignalType",
    "get_agent_by_type",
    "get_agent_dependencies",
    "get_agent_nodes",
    "get_agents_list",
    "resolve_agent_execution_order",
]