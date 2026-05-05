"""
消息传递工具

处理智能体间的消息发送和接收。
"""

import asyncio
import logging
from typing import Any

from src.collaboration_tools_core._session import (
    _message_buses,
    _session_lock,
)

logger = logging.getLogger(__name__)


def send_agent_message(
    session_id: str,
    from_agent: str,
    to_agent: str,
    message_type: str,
    content: dict[str, Any],
) -> str:
    """发送智能体消息"""
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"
        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.send_message(from_agent, to_agent, message_type, content)
        )
        add_background_task(task)
        return f"Message sent: {from_agent} -> {to_agent}\nType: {message_type}"
    except RuntimeError:
        return "Message sending requires async context. Use in AgentLoop."


def broadcast_message(
    session_id: str,
    from_agent: str,
    message_type: str,
    content: dict[str, Any],
    exclude_self: bool = True,
) -> str:
    """广播消息"""
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"
        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.broadcast(from_agent, message_type, content, exclude_self)
        )
        add_background_task(task)
        return f"Message broadcast from: {from_agent}\nType: {message_type}"
    except RuntimeError:
        return "Broadcast requires async context. Use in AgentLoop."


def receive_agent_messages(
    session_id: str,
    agent_id: str,
    message_types: list[str] | None = None,
) -> str:
    """接收智能体消息"""
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"
        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.receive_messages(agent_id, message_types)
        )
        add_background_task(task)
        return f"Message receiving started for agent: {agent_id}"
    except RuntimeError:
        count = message_bus.get_message_count()
        return f"Messages available: {count}. Use async context for full retrieval."


def register_message_handler(
    session_id: str,
    message_type: str,
    handler_name: str,
) -> str:
    """注册消息处理器"""
    from collections.abc import Callable

    # 预定义处理器
    predefined_handlers: dict[str, Callable[[dict], None]] = {
        "log": lambda msg: logger.info(
            f"Message received: {msg.get('type', 'unknown')} - {msg.get('content', '')[:100]}"
        ),
        "count": lambda msg: None,
        "echo": lambda msg: logger.info(
            f"[Message] {msg.get('type', 'unknown')}: {msg.get('content', '')}"
        ),
    }

    if handler_name not in predefined_handlers:
        available = list(predefined_handlers.keys())
        return f"Error: Unknown handler '{handler_name}'. Available handlers: {available}"

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"
        message_bus = _message_buses[session_id]

    try:
        handler = predefined_handlers[handler_name]
        message_bus.register_handler(message_type, handler)
        return f"Handler registered: type={message_type}, handler={handler_name}"
    except Exception as e:
        return f"Error registering handler: {type(e).__name__}: {e}"