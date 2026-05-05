"""多智能体协作模块 - 消息总线

InterAgentMessageBus: 智能体间消息传递总线

基于 SessionEventStream 实现的消息传递机制：
- 发送消息：记录到 Session
- 接收消息：从 Session 筛选
- 广播消息：批量发送

核心特性：
- 异步消息传递
- 类型订阅机制
- 广播支持

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


class InterAgentMessageBus:
    """智能体间消息传递总线

    基于 SessionEventStream 实现的消息传递机制：
    - 发送消息：记录到 Session
    - 接收消息：从 Session 筛选
    - 广播消息：批量发送

    核心特性：
    - 异步消息传递
    - 类型订阅机制
    - 广播支持
    """

    def __init__(self, session: SessionEventStream):
        """初始化消息总线

        Args:
            session: Session 事件流
        """
        self.session = session
        self._message_handlers: dict[str, list[Callable]] = {}
        self._pair_ids: list[str] = []

        logger.info(f"InterAgentMessageBus initialized: session={session.session_id}")

    def set_pair_ids(self, pair_ids: list[str]) -> None:
        """设置智能体 ID 列表（用于广播）"""
        self._pair_ids = pair_ids

    def register_handler(
        self, message_type: str, handler: Callable[[dict[str, Any]], Any]
    ) -> None:
        """注册消息处理器

        Args:
            message_type: 消息类型
            handler: 处理函数
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
        logger.debug(f"Handler registered: type={message_type}")

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        content: dict[str, Any],
    ) -> int:
        """发送消息

        Args:
            from_agent: 发送方 ID
            to_agent: 接收方 ID
            message_type: 消息类型
            content: 消息内容

        Returns:
            事件 ID
        """
        message_id = self.session.emit_event(
            "inter_agent_message",
            {
                "from": from_agent,
                "to": to_agent,
                "type": message_type,
                "content": content,
                "timestamp": time.time(),
            },
        )

        logger.debug(f"Message sent: {from_agent} -> {to_agent}, type={message_type}")
        return message_id

    async def receive_messages(
        self, agent_id: str, message_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """接收消息

        Args:
            agent_id: 接收方 ID
            message_types: 过滤的消息类型（可选）

        Returns:
            消息列表
        """
        # 从 Session 筛选消息
        messages = [
            e["data"]
            for e in self.session.get_events()
            if e["type"] == "inter_agent_message" and e["data"].get("to") == agent_id
        ]

        # 类型过滤
        if message_types:
            messages = [m for m in messages if m.get("type") in message_types]

        # 处理消息
        for msg in messages:
            handlers = self._message_handlers.get(msg.get("type", ""), [])
            for handler in handlers:
                try:
                    # 支持同步和异步处理器
                    if asyncio.iscoroutinefunction(handler):
                        await handler(msg)
                    else:
                        handler(msg)
                except Exception as e:
                    logger.warning(f"Handler error: {e}")

        return messages

    async def broadcast(
        self,
        from_agent: str,
        message_type: str,
        content: dict[str, Any],
        exclude_self: bool = True,
    ) -> list[int]:
        """广播消息

        Args:
            from_agent: 发送方 ID
            message_type: 消息类型
            content: 消息内容
            exclude_self: 是否排除自己

        Returns:
            事件 ID 列表
        """
        message_ids: list[int] = []
        targets = [
            pid for pid in self._pair_ids if not (exclude_self and pid == from_agent)
        ]

        for target in targets:
            message_id = await self.send_message(
                from_agent, target, message_type, content
            )
            message_ids.append(message_id)

        logger.debug(f"Broadcast: {from_agent} -> {len(targets)} targets")
        return message_ids

    def get_message_count(self) -> int:
        """获取消息总数"""
        return len(
            [e for e in self.session.get_events() if e["type"] == "inter_agent_message"]
        )

    def clear_handlers(self) -> None:
        """清除所有处理器"""
        self._message_handlers.clear()
        logger.debug("All handlers cleared")
