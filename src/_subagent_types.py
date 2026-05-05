"""
Subagent 类型定义

包含枚举、状态、数据类定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum


class SubagentType(Enum):
    """Subagent 类型枚举"""

    EXPLORE = "explore"  # 只读探索：搜索文件、阅读代码
    REVIEW = "review"  # 审查验证：只读 + 代码执行
    IMPLEMENT = "implement"  # 实现执行：全权限
    PLAN = "plan"  # 规划分析：只读 + 记忆写入


class SubagentStatus(StrEnum):
    """Subagent 状态枚举"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败
    TIMEOUT = "timeout"  # 执行超时


@dataclass
class SubagentState:
    """Subagent 状态"""

    id: str
    subagent_type: SubagentType
    status: SubagentStatus | str  # 使用枚举或字符串（兼容性）
    prompt: str
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    iterations: int = 0
    parent_session_id: str | None = None


class SubagentResult:
    """Subagent 执行结果"""

    def __init__(self, state: SubagentState):
        self.state = state

    @property
    def success(self) -> bool:
        return self.state.status == "completed"

    @property
    def result(self) -> str | None:
        return self.state.result

    @property
    def error(self) -> str | None:
        return self.state.error

    @property
    def summary(self) -> str:
        """返回结果摘要"""
        if self.success:
            # 截断过长的结果
            r = self.result or ""
            if len(r) > 500:
                return r[:500] + "...(truncated)"
            return r
        return f"[{self.state.status.upper()}] {self.error}"

    def to_dict(self) -> dict:
        return {
            "id": self.state.id,
            "type": self.state.subagent_type.value,
            "status": self.state.status,
            "result": self.result,
            "error": self.error,
            "iterations": self.state.iterations,
            "duration": (
                (self.state.completed_at - self.state.started_at).total_seconds()
                if self.state.completed_at and self.state.started_at
                else None
            ),
        }


def _get_subagent_type_key(subagent_type: SubagentType | str) -> str:
    """获取 SubagentType 的字符串键（用于字典查找）

    Args:
        subagent_type: SubagentType 枚举或字符串

    Returns:
        str: 类型键（"explore", "review", "implement", "plan"）
    """
    if isinstance(subagent_type, SubagentType):
        return subagent_type.value
    return subagent_type