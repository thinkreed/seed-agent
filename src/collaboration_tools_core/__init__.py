"""
协作工具核心模块

包含协作工具的类型、会话管理、三种协作模式和消息传递。
"""

from src.collaboration_tools_core._message import (
    broadcast_message,
    receive_agent_messages,
    register_message_handler,
    send_agent_message,
)
from src.collaboration_tools_core._multi_brain_one_hand import (
    collaborative_improve,
    multi_angle_analysis,
    setup_multi_brain_one_hand,
)
from src.collaboration_tools_core._one_brain_multi_hand import (
    cross_environment_execute,
    cross_environment_test,
    setup_one_brain_multi_hand,
)
from src.collaboration_tools_core._session import (
    _collaboration_sessions,  # 向后兼容
    _message_buses,  # 向后兼容
    _orchestrators,  # 向后兼容
    create_collaboration_session,
    destroy_collaboration_session,
    get_collaboration_status,
    get_message_bus_registry,
    get_orchestrator_registry,
    get_session_registry,
)

__all__ = [
    "_collaboration_sessions",  # 向后兼容
    "_message_buses",  # 向后兼容
    "_orchestrators",  # 向后兼容
    "broadcast_message",
    "collaborative_improve",
    # 会话管理
    "create_collaboration_session",
    "cross_environment_execute",
    "cross_environment_test",
    "destroy_collaboration_session",
    "get_collaboration_status",
    "get_message_bus_registry",
    "get_orchestrator_registry",
    "get_session_registry",
    "multi_angle_analysis",
    "receive_agent_messages",
    "register_message_handler",
    # 消息传递
    "send_agent_message",
    # 多脑一手
    "setup_multi_brain_one_hand",
    # 一脑多手
    "setup_one_brain_multi_hand",
]