"""多智能体协作模块 - 数据类型定义

定义核心数据结构：
- CollaborationMode: 协作模式枚举
- AgentInstance: 智能体实例
- AnalysisResult: 分析结果
- ExecutionResult: 执行结果
- CoordinationResult: 协调结果

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.sandbox import Sandbox


class CollaborationMode(StrEnum):
    """协作模式枚举"""

    MULTI_BRAIN_ONE_HAND = "multi_brain_one_hand"  # 多脑一手
    ONE_BRAIN_MULTI_HAND = "one_brain_multi_hand"  # 一脑多手
    MULTI_BRAIN_MULTI_HAND = "multi_brain_multi_hand"  # 多脑多手


@dataclass
class AgentInstance:
    """智能体实例"""

    id: str
    llm_client: "LLMClient"
    sandbox: "Sandbox | None" = None
    perspective: str | None = None  # 分析视角（多脑一手）
    label: str | None = None  # 工作台标签（一脑多手）
    status: str = "idle"  # idle, running, completed, failed


@dataclass
class AnalysisResult:
    """分析结果"""

    perspective: str
    result: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """执行结果"""

    agent_id: str
    label: str
    results: list[str]
    success: bool
    error: str | None = None


@dataclass
class CoordinationResult:
    """协调结果"""

    task: str
    agent_results: list[dict[str, Any]]
    merged_result: dict[str, Any]
    session_events: list[dict[str, Any]]
