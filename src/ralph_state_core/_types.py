"""
RalphState 数据类定义

提供 Ralph Loop 状态的数据结构。
"""

import time


class RalphState:
    """Ralph Loop 状态数据类"""

    def __init__(
        self,
        iteration: int = 0,
        accumulated_duration: float = 0.0,
        start_time: float = 0.0,
        last_response: str = "",
        task_file: str = "",
        completion_type: str = "",
    ):
        self.iteration = iteration
        self.accumulated_duration = accumulated_duration
        self.start_time = start_time or time.time()
        self.last_response = last_response
        self.task_file = task_file
        self.completion_type = completion_type

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "iteration": self.iteration,
            "accumulated_duration": self.accumulated_duration,
            "start_time": self.start_time,
            "last_response": self.last_response[:500] if self.last_response else "",
            "timestamp": time.time(),
            "task_file": self.task_file,
            "completion_type": self.completion_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RalphState":
        """从字典创建"""
        return cls(
            iteration=data.get("iteration", 0),
            accumulated_duration=data.get("accumulated_duration", 0),
            start_time=data.get("start_time", time.time()),
            last_response=data.get("last_response", ""),
            task_file=data.get("task_file", ""),
            completion_type=data.get("completion_type", ""),
        )