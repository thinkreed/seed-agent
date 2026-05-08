"""
Harness 异常和结果类型

从 harness.py 拆分的类型定义：
- MaxIterationsExceededError: 超过最大迭代次数
- LoopDetectedError: 循环检测错误
- CycleResult: 单轮循环结果类型
"""

from src.harness._loop_detection import LoopType


class MaxIterationsExceededError(Exception):
    """超过最大迭代次数"""

    def __init__(self, iterations: int) -> None:
        super().__init__(f"Harness exceeded maximum iterations ({iterations})")
        self.iterations = iterations


class LoopDetectedError(Exception):
    """检测到循环调用"""

    def __init__(self, loop_type: LoopType, tool_name: str | None = None, count: int = 0) -> None:
        message = f"Loop detected: {loop_type.name}"
        if tool_name:
            message += f" (tool: {tool_name})"
        if count:
            message += f" (count: {count})"
        super().__init__(message)
        self.loop_type = loop_type
        self.tool_name = tool_name
        self.count = count


class CycleResult(dict):
    """单轮循环结果（TypedDict 兼容）"""
    pass


__all__ = ["CycleResult", "LoopDetectedError", "MaxIterationsExceededError"]