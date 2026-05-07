"""后台任务类型定义模块

包含 TaskStatus 枚举和 BackgroundTaskEntry 数据类。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.abort_signal import AbortController


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 执行超时


@dataclass
class BackgroundTaskEntry:
    """后台任务条目"""

    task_id: str
    prompt: str
    status: TaskStatus
    abort_controller: AbortController
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt[:100] + "..."
            if len(self.prompt) > 100
            else self.prompt,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result[:200] + "..."
            if self.result and len(self.result) > 200
            else self.result,
            "error": self.error,
        }


# 优雅等待期（秒）
CANCEL_GRACE_SECONDS = 5


__all__ = ["CANCEL_GRACE_SECONDS", "BackgroundTaskEntry", "TaskStatus"]