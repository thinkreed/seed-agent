"""
Agent 类型定义

基于 ai-hedge-fund ANALYST_CONFIG 设计，提供 Agent 元数据类型：
- AgentSignalType: 信号类型枚举
- AgentSignal: 统一信号输出格式
- AgentConfig: Agent 配置元数据

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


__all__ = [
    "AgentConfig",
    "AgentSignal",
    "AgentSignalType",
]