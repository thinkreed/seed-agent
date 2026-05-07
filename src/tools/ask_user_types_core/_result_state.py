"""
结果和状态管理

包含：
- AskUserResult: Ask User 结果
- AskUserState: 状态管理
- 全局状态管理函数

核心特性：
- 取消/超时状态
- 线程安全
- 全局单例
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from ._request import AskUserRequest, UserResponse


@dataclass
class AskUserResult:
    """Ask User 结果"""

    request_id: str
    responses: list[UserResponse] = field(default_factory=list)
    cancelled: bool = False
    timeout: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "responses": [r.to_dict() for r in self.responses],
            "cancelled": self.cancelled,
            "timeout": self.timeout,
        }

    @classmethod
    def cancelled_result(cls, request_id: str) -> AskUserResult:
        return cls(request_id=request_id, cancelled=True)

    @classmethod
    def timeout_result(cls, request_id: str) -> AskUserResult:
        return cls(request_id=request_id, timeout=True)

    def get_selected_values(self) -> list[str]:
        values = []
        for response in self.responses:
            values.extend(response.selected)
        return values

    def get_first_selected(self) -> str | None:
        if self.responses and self.responses[0].selected:
            return self.responses[0].selected[0]
        return None


@dataclass
class AskUserState:
    """Ask User 状态管理"""

    pending_request: AskUserRequest | None = None
    waiting_event: asyncio.Event = field(default_factory=asyncio.Event)
    response: AskUserResult | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_request(self, request: AskUserRequest) -> None:
        with self._lock:
            self.pending_request = request
            self.response = None
            self.waiting_event.clear()

    def inject_response(self, response: AskUserResult) -> None:
        with self._lock:
            self.response = response
            self.pending_request = None
            self.waiting_event.set()

    def clear(self) -> None:
        with self._lock:
            self.pending_request = None
            self.response = None
            self.waiting_event.clear()

    def is_waiting(self) -> bool:
        with self._lock:
            return self.pending_request is not None


# 全局状态管理器（单例）
_global_ask_user_state: AskUserState | None = None
_global_state_lock: threading.Lock = threading.Lock()


def get_ask_user_state() -> AskUserState:
    """获取全局状态管理器（线程安全）"""
    global _global_ask_user_state
    with _global_state_lock:
        if _global_ask_user_state is None:
            _global_ask_user_state = AskUserState()
        return _global_ask_user_state


def reset_ask_user_state() -> None:
    """重置全局状态管理器"""
    global _global_ask_user_state
    with _global_state_lock:
        if _global_ask_user_state:
            _global_ask_user_state.clear()
        _global_ask_user_state = AskUserState()


def clear_ask_user_state() -> None:
    """清理当前等待状态"""
    state = get_ask_user_state()
    state.clear()


def get_pending_ask_user_request() -> AskUserRequest | None:
    """获取待处理的请求"""
    state = get_ask_user_state()
    return state.pending_request


__all__ = [
    "AskUserResult",
    "AskUserState",
    "clear_ask_user_state",
    "get_ask_user_state",
    "get_pending_ask_user_request",
    "reset_ask_user_state",
]