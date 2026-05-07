"""TTRL 枚举和数据类型

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JudgementType(Enum):
    """执行结果判断类型"""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class MemorySource(Enum):
    """记忆来源类型（用于 TTRL）"""

    EXECUTOR = "executor"  # Executor 执行结果
    PLANNER = "planner"  # Planner 规划结果
    TOOL_CALL = "tool_call"  # 工具调用结果
    USER_FEEDBACK = "user_feedback"  # 用户反馈


@dataclass
class ExecutionTrace:
    """执行轨迹

    记录一次任务执行的完整信息，用于 TTRL 分析。
    """

    trace_id: str
    task_description: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    judgement: JudgementType = JudgementType.UNKNOWN
    source: MemorySource = MemorySource.EXECUTOR
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    success_indicators: list[str] = field(default_factory=list)
    failure_indicators: list[str] = field(default_factory=list)


@dataclass
class MemoryEntry:
    """记忆条目（用于整合）

    MIA 记忆结构：
    - question: 任务描述
    - workflow_summary: 工作流摘要
    - plan: 执行计划
    - judgement: 正确性判断
    - usage_count: 使用次数
    - success_count: 成功次数
    - win_rate: 胜率
    """

    question: str
    workflow_summary: str
    plan: str = ""
    judgement: JudgementType = JudgementType.CORRECT
    source: MemorySource = MemorySource.EXECUTOR
    data_id: str = ""
    usage_count: int = 1
    success_count: int = 1
    win_rate: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ConsolidationResult:
    """记忆整合结果"""

    total_traces: int
    correct_count: int
    incorrect_count: int
    new_memories: int
    updated_memories: int
    skipped_memories: int
    errors: list[str] = field(default_factory=list)


__all__ = [
    "ConsolidationResult",
    "ExecutionTrace",
    "JudgementType",
    "MemoryEntry",
    "MemorySource",
]