"""
用户交互模块

提供用户交互方法：
- inject_user_input: 注入用户响应
- cancel_current_execution: 取消当前执行
- get_abort_signal: 获取取消信号
- set_autonomous_mode: 设置自主探索模式
- inject_system_message: 注入系统消息

核心特性：
- 取消控制
- 自主模式切换
- 系统消息注入
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.abort_signal import AbortController, AbortSignal
from src.tools.ask_user_types import AskUserResult

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger(__name__)


class UserInteractionMixin:
    """用户交互功能 Mixin

    提供用户交互相关方法。
    需要与 AgentLoop 配合使用。
    """

    # 声明 Mixin 依赖的属性（类型检查）
    if False:  # TYPE_CHECKING 替代
        _abort_controller: AbortController
        _user_input_event: asyncio.Event
        _pending_user_response: AskUserResult | None
        harness: Any
        session: Any

    def inject_user_input(self: "AgentLoop", response: AskUserResult) -> None:
        """注入用户响应"""
        self._pending_user_response = response
        self._user_input_event.set()

    def cancel_current_execution(self: "AgentLoop") -> None:
        """取消当前执行"""
        self._abort_controller.abort(reason="user_interrupt")
        self._user_input_event.set()

    def get_abort_signal(self: "AgentLoop") -> AbortSignal:
        """获取取消信号"""
        return self._abort_controller.signal

    def set_autonomous_mode(
        self: "AgentLoop", enabled: bool, skip_response: str | None = None
    ) -> None:
        """设置自主探索模式"""
        self.harness.set_autonomous_mode(enabled, skip_response)
        logger.info(f"AgentLoop autonomous mode: {enabled}")

    def inject_system_message(self: "AgentLoop", message: str) -> None:
        """注入系统消息"""
        from src.session_event_stream import EventType

        self.session.emit_event(
            EventType.SYSTEM_MESSAGE,
            {"content": message, "source": "autonomous_budget_warning"},
        )
        logger.info(f"System message injected: {message[:100]}...")