"""定时任务定义模块

包含 ScheduledTask 类定义。
"""

import time


class ScheduledTask:
    """定时任务定义"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        interval_seconds: int,
        prompt: str,
        last_run: float = 0,
        enabled: bool = True,
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.interval_seconds = interval_seconds
        self.prompt = prompt
        self.last_run = last_run
        self.enabled = enabled

    def should_run(self) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        return time.time() - self.last_run >= self.interval_seconds

    def mark_run(self) -> None:
        """标记已执行"""
        self.last_run = time.time()

    def to_dict(self) -> dict:
        """序列化"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "interval_seconds": self.interval_seconds,
            "prompt": self.prompt,
            "last_run": self.last_run,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        """反序列化"""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            interval_seconds=data["interval_seconds"],
            prompt=data["prompt"],
            last_run=data.get("last_run", 0),
            enabled=data.get("enabled", True),
        )


__all__ = ["ScheduledTask"]