"""
协作工具核心模块

包含协作工具的类型、会话管理、三种协作模式和消息传递。
"""

from src.collaboration_tools_core._session import (
    create_collaboration_session,
    destroy_collaboration_session,
    get_collaboration_status,
    get_session_registry,
    get_orchestrator_registry,
    get_message_bus_registry,
)
from src.collaboration_tools_core._multi_brain_one_hand import (
    setup_multi_brain_one_hand,
    multi_angle_analysis,
    collaborative_improve,
)
from src.collaboration_tools_core._one_brain_multi_hand import (
    setup_one_brain_multi_hand,
    cross_environment_execute,
    cross_environment_test,
)
from src.collaboration_tools_core._message import (
    send_agent_message,
    broadcast_message,
    receive_agent_messages,
    register_message_handler,
)

__all__ = [
    # 会话管理
    "create_collaboration_session",
    "get_collaboration_status",
    "destroy_collaboration_session",
    "get_session_registry",
    "get_orchestrator_registry",
    "get_message_bus_registry",
    # 多脑一手
    "setup_multi_brain_one_hand",
    "multi_angle_analysis",
    "collaborative_improve",
    # 一脑多手
    "setup_one_brain_multi_hand",
    "cross_environment_execute",
    "cross_environment_test",
    # 消息传递
    "send_agent_message",
    "broadcast_message",
    "receive_agent_messages",
    "register_message_handler",
]