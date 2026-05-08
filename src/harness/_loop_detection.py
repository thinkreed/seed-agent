"""循环检测服务 - 检测 LLM 循环调用（相同工具/参数/空响应）。

阈值：same_tool=3, same_args=3, empty_response=5。参考: Qwen Code LoopDetectionService
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class LoopType(Enum):
    """循环类型"""
    SAME_TOOL = auto()
    SAME_ARGS = auto()
    EMPTY_RESPONSE = auto()
    REPEATED_PATTERN = auto()


@dataclass
class LoopEvent:
    """循环检测事件"""
    loop_type: LoopType
    tool_name: str | None = None
    args: dict | None = None
    count: int = 0
    message: str = ""


@dataclass
class LoopDetectionConfig:
    """循环检测配置"""
    max_consecutive_same_tool: int = 3
    max_consecutive_same_args: int = 3
    max_consecutive_empty_response: int = 5
    history_window_size: int = 20
    enabled: bool = True


class LoopDetectionService:
    """循环检测服务 - 滑动窗口检测循环模式"""

    def __init__(self, config: LoopDetectionConfig | None = None):
        self.config = config or LoopDetectionConfig()
        self._tool_call_history: deque[dict[str, Any]] = deque(
            maxlen=self.config.history_window_size
        )
        self._response_history: deque[str] = deque(maxlen=self.config.history_window_size)
        self._last_loop_type: LoopType | None = None

    def add_tool_call(self, tool_name: str, args: dict[str, Any]) -> LoopEvent | None:
        """添加工具调用并检测循环"""
        if not self.config.enabled:
            return None
        call_record = {"tool_name": tool_name, "args": args}
        self._tool_call_history.append(call_record)
        loop_event = self._check_same_tool_loop()
        if loop_event:
            self._last_loop_type = loop_event.loop_type
            return loop_event
        loop_event = self._check_same_args_loop()
        if loop_event:
            self._last_loop_type = loop_event.loop_type
            return loop_event
        return None

    def add_response(self, response: str) -> LoopEvent | None:
        """添加响应并检测空响应循环"""
        if not self.config.enabled:
            return None
        self._response_history.append(response)
        if not response or not response.strip():
            loop_event = self._check_empty_response_loop()
            if loop_event:
                self._last_loop_type = loop_event.loop_type
                return loop_event
        return None

    def _check_same_tool_loop(self) -> LoopEvent | None:
        """检测连续相同工具调用"""
        if len(self._tool_call_history) < self.config.max_consecutive_same_tool:
            return None
        recent_calls = list(self._tool_call_history)[-self.config.max_consecutive_same_tool:]
        tool_names = [c["tool_name"] for c in recent_calls]
        if len(set(tool_names)) == 1:
            tool_name = tool_names[0]
            return LoopEvent(
                loop_type=LoopType.SAME_TOOL,
                tool_name=tool_name,
                count=self.config.max_consecutive_same_tool,
                message=f"连续 {self.config.max_consecutive_same_tool} 次调用相同工具: {tool_name}",
            )
        return None

    def _check_same_args_loop(self) -> LoopEvent | None:
        """检测连续相同参数调用"""
        if len(self._tool_call_history) < self.config.max_consecutive_same_args:
            return None
        recent_calls = list(self._tool_call_history)[-self.config.max_consecutive_same_args:]
        args_list = [c["args"] for c in recent_calls]
        args_str_list = [str(sorted(c.items()) if isinstance(c, dict) else c) for c in args_list]
        if len(set(args_str_list)) == 1:
            tool_name = recent_calls[0]["tool_name"]
            return LoopEvent(
                loop_type=LoopType.SAME_ARGS,
                tool_name=tool_name,
                args=args_list[0],
                count=self.config.max_consecutive_same_args,
                message=f"连续 {self.config.max_consecutive_same_args} 次使用相同参数调用: {tool_name}",
            )
        return None

    def _check_empty_response_loop(self) -> LoopEvent | None:
        """检测连续空响应"""
        if len(self._response_history) < self.config.max_consecutive_empty_response:
            return None
        recent_responses = list(self._response_history)[-self.config.max_consecutive_empty_response:]
        if all(not r or not r.strip() for r in recent_responses):
            return LoopEvent(
                loop_type=LoopType.EMPTY_RESPONSE,
                count=self.config.max_consecutive_empty_response,
                message=f"连续 {self.config.max_consecutive_empty_response} 次空响应",
            )
        return None

    def get_last_loop_type(self) -> LoopType | None:
        """获取最后一次检测到的循环类型"""
        return self._last_loop_type

    def clear(self) -> None:
        """清空历史"""
        self._tool_call_history.clear()
        self._response_history.clear()
        self._last_loop_type = None

    def get_status(self) -> dict[str, Any]:
        """获取状态"""
        return {
            "enabled": self.config.enabled,
            "tool_call_count": len(self._tool_call_history),
            "response_count": len(self._response_history),
            "last_loop_type": self._last_loop_type.value if self._last_loop_type else None,
        }


__all__ = ["LoopDetectionConfig", "LoopDetectionService", "LoopEvent", "LoopType"]