"""钩子执行结果和统计类型

包含 HookExecutionResult, HookTriggerReport, HookStats。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookExecutionResult:
    """单个钩子执行结果"""

    hook_id: str
    status: str  # "success" | "failed" | "skipped"
    duration_ms: float
    result: Any | None = None
    error: str | None = None


@dataclass
class HookTriggerReport:
    """钩子触发报告"""

    hook_point: str
    hooks_count: int
    hooks_executed: int
    hooks_failed: int
    hooks_skipped: int
    results: list[HookExecutionResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_point": self.hook_point,
            "hooks_count": self.hooks_count,
            "hooks_executed": self.hooks_executed,
            "hooks_failed": self.hooks_failed,
            "hooks_skipped": self.hooks_skipped,
            "total_duration_ms": self.total_duration_ms,
            "results": [
                {
                    "hook_id": r.hook_id,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


@dataclass
class HookStats:
    """钩子执行统计"""

    hook_id: str
    hook_point: str
    priority: int
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    skipped_calls: int = 0
    total_duration_ms: float = 0.0
    last_call_time: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_id": self.hook_id,
            "hook_point": self.hook_point,
            "priority": self.priority,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "skipped_calls": self.skipped_calls,
            "success_rate": self.success_calls / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "avg_duration_ms": self.total_duration_ms / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "last_call_time": self.last_call_time,
            "last_error": self.last_error,
        }


__all__ = ["HookExecutionResult", "HookTriggerReport", "HookStats"]