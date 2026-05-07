"""
AgentConfig 注册机制

基于 ai-hedge-fund ANALYST_CONFIG 设计，提供 Agent 元数据注册和发现功能：
- AGENT_CONFIG: Agent 元数据字典（display_name, description, style, capabilities, order）
- get_agent_nodes(): 获取 Agent 名称到配置的映射
- get_agents_list(): 获取 Agent 列表用于 API 响应
- AgentSignal: 统一信号输出格式（signal, confidence, reasoning）

Wiki 知识落地 P3 (基于 ai-hedge-fund Agent 系统设计)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src._subagent_types import SubagentType


class AgentSignalType(Enum):
    """Agent 信号类型枚举

    基于 ai-hedge-fund 的信号输出格式设计：
    - Bullish: 看多/正面信号
    - Bearish: 看空/负面信号
    - Neutral: 中立/不确定信号
    """

    Bullish = "bullish"
    Bearish = "bearish"
    Neutral = "neutral"


@dataclass
class AgentSignal:
    """Agent 信号输出格式

    基于 ai-hedge-fund 的 AgentSignal 设计，标准化 Agent 输出：
    - signal: 信号类型（bullish/bearish/neutral）
    - confidence: 置信度（0-100）
    - reasoning: 分析推理描述
    """

    signal: AgentSignalType
    confidence: int = 50  # 0-100
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal": self.signal.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class AgentConfig:
    """Agent 配置元数据

    基于 ai-hedge-fund ANALYST_CONFIG 设计，提供丰富的 Agent 元数据：
    - display_name: 显示名称（用于 UI）
    - description: 简短描述
    - style: 工作风格/方法论（类似 investing_style）
    - capabilities: 能力标签列表
    - subagent_type: 对应的 SubagentType
    - order: 显示顺序
    - prerequisites: 前置依赖 Agent（基于 Shannon 设计）
    """

    display_name: str
    description: str
    style: str = ""
    capabilities: list[str] = field(default_factory=list)
    subagent_type: SubagentType = SubagentType.EXPLORE
    order: int = 0
    prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "description": self.description,
            "style": self.style,
            "capabilities": self.capabilities,
            "subagent_type": self.subagent_type.value,
            "order": self.order,
            "prerequisites": self.prerequisites,
        }


# === Agent 注册表 ===

AGENT_CONFIG: dict[str, AgentConfig] = {
    # === 探索类 Agent ===
    "explore": AgentConfig(
        display_name="Explorer",
        description="只读探索 Agent",
        style="搜索文件、阅读代码、分析结构，不做任何修改",
        capabilities=["read_only", "search", "analyze"],
        subagent_type=SubagentType.EXPLORE,
        order=1,
        prerequisites=[],
    ),
    # === 审查类 Agent ===
    "review": AgentConfig(
        display_name="Reviewer",
        description="审查验证 Agent",
        style="验证实现质量、运行测试、检查安全，可执行代码",
        capabilities=["read_only", "execute", "test", "security_check"],
        subagent_type=SubagentType.REVIEW,
        order=2,
        prerequisites=["explore"],
    ),
    # === 实现类 Agent ===
    "implement": AgentConfig(
        display_name="Implementer",
        description="实现执行 Agent",
        style="编写代码、修改文件、解决问题，全权限执行",
        capabilities=["write", "execute", "modify", "create"],
        subagent_type=SubagentType.IMPLEMENT,
        order=3,
        prerequisites=["explore", "review"],
    ),
    # === 规划类 Agent ===
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
    """获取 Agent 名称到 (类型键, 配置) 的映射

    基于 ai-hedge-fund get_analyst_nodes() 设计

    Returns:
        dict[str, tuple[str, AgentConfig]]: Agent 名称到配置的映射
    """
    return {
        key: (f"{key}_agent", config)
        for key, config in AGENT_CONFIG.items()
    }


def get_agents_list() -> list[dict[str, Any]]:
    """获取 Agent 列表用于 API 响应

    基于 ai-hedge-fund get_agents_list() 设计，按 order 排序

    Returns:
        list[dict]: Agent 元数据列表
    """
    return [
        config.to_dict()
        for key, config in sorted(
            AGENT_CONFIG.items(),
            key=lambda x: x[1].order,
        )
    ]


def get_agent_by_type(subagent_type: SubagentType) -> AgentConfig | None:
    """根据 SubagentType 获取 Agent 配置

    Args:
        subagent_type: SubagentType 枚举值

    Returns:
        AgentConfig | None: 匹配的配置，或 None
    """
    for config in AGENT_CONFIG.values():
        if config.subagent_type == subagent_type:
            return config
    return None


def get_agent_dependencies(agent_key: str) -> list[str]:
    """获取 Agent 的前置依赖列表

    基于 Shannon 的 Agent 依赖图设计

    Args:
        agent_key: Agent 配置键名

    Returns:
        list[str]: 前置依赖 Agent 键名列表
    """
    config = AGENT_CONFIG.get(agent_key)
    if config:
        return config.prerequisites
    return []


def resolve_agent_execution_order(agent_keys: list[str]) -> list[str]:
    """解析 Agent 执行顺序（基于依赖图）

    基于 Shannon 的依赖图拓扑排序设计

    Args:
        agent_keys: 需要执行的 Agent 键名列表

    Returns:
        list[str]: 按依赖顺序排列的 Agent 键名列表
    """
    # 构建依赖图
    visited: set[str] = set()
    result: list[str] = []

    def visit(key: str) -> None:
        if key in visited:
            return
        visited.add(key)

        # 先访问所有前置依赖
        for prereq in get_agent_dependencies(key):
            if prereq in agent_keys:  # 只处理请求列表中的 Agent
                visit(prereq)

        result.append(key)

    for key in agent_keys:
        visit(key)

    return result


__all__ = [
    # 类型定义
    "AgentSignalType",
    "AgentSignal",
    "AgentConfig",
    # 注册表
    "AGENT_CONFIG",
    # 工具函数
    "get_agent_nodes",
    "get_agents_list",
    "get_agent_by_type",
    "get_agent_dependencies",
    "resolve_agent_execution_order",
]