"""
协作工具集 - 为 AgentLoop 提供多智能体协作操作接口

核心工具:
- create_collaboration_session: 创建协作会话
- multi_angle_analysis: 多脑一手模式多角度分析
- cross_environment_execute: 一脑多手模式跨环境执行
- coordinated_task: 多脑多手模式协调任务
- send_agent_message: 智能体间消息传递
- broadcast_message: 广播消息
- get_collaboration_status: 获取协作状态

模块拆分:
- collaboration_tools_core/_session.py: 会话管理
- collaboration_tools_core/_multi_brain_one_hand.py: 多脑一手模式
- collaboration_tools_core/_one_brain_multi_hand.py: 一脑多手模式
- collaboration_tools_core/_multi_brain_multi_hand.py: 多脑多手模式
- collaboration_tools_core/_message.py: 消息传递
"""

import logging
from typing import TYPE_CHECKING

from src.collaboration_tools_core import (
    _collaboration_sessions,  # 向后兼容
    _message_buses,  # 向后兼容
    _orchestrators,  # 向后兼容
    broadcast_message,
    collaborative_improve,
    create_collaboration_session,
    cross_environment_execute,
    cross_environment_test,
    destroy_collaboration_session,
    get_collaboration_status,
    multi_angle_analysis,
    receive_agent_messages,
    register_message_handler,
    send_agent_message,
    setup_multi_brain_one_hand,
    setup_one_brain_multi_hand,
)
from src.collaboration_tools_core._multi_brain_multi_hand import (
    coordinated_task,
    setup_multi_brain_multi_hand,
)

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)


def register_tools(registry: "ToolRegistry") -> None:
    """注册所有协作工具到 Registry"""
    # 会话管理
    registry.register("create_collaboration_session", create_collaboration_session)
    registry.register("get_collaboration_status", get_collaboration_status)
    registry.register("destroy_collaboration_session", destroy_collaboration_session)

    # 多脑一手模式
    registry.register("setup_multi_brain_one_hand", setup_multi_brain_one_hand)
    registry.register("multi_angle_analysis", multi_angle_analysis)
    registry.register("collaborative_improve", collaborative_improve)

    # 一脑多手模式
    registry.register("setup_one_brain_multi_hand", setup_one_brain_multi_hand)
    registry.register("cross_environment_execute", cross_environment_execute)
    registry.register("cross_environment_test", cross_environment_test)

    # 多脑多手模式
    registry.register("setup_multi_brain_multi_hand", setup_multi_brain_multi_hand)
    registry.register("coordinated_task", coordinated_task)

    # 消息传递
    registry.register("send_agent_message", send_agent_message)
    registry.register("broadcast_message", broadcast_message)
    registry.register("receive_agent_messages", receive_agent_messages)
    registry.register("register_message_handler", register_message_handler)

    logger.info("Collaboration tools registered: 15 tools")


__all__ = [
    # 向后兼容（测试需要）
    "_collaboration_sessions",
    "_message_buses",
    "_orchestrators",
    # 会话管理
    "create_collaboration_session",
    "destroy_collaboration_session",
    "get_collaboration_status",
    # 多脑一手
    "setup_multi_brain_one_hand",
    "multi_angle_analysis",
    "collaborative_improve",
    # 一脑多手
    "setup_one_brain_multi_hand",
    "cross_environment_execute",
    "cross_environment_test",
    # 多脑多手
    "setup_multi_brain_multi_hand",
    "coordinated_task",
    # 消息传递
    "send_agent_message",
    "broadcast_message",
    "receive_agent_messages",
    "register_message_handler",
    # 注册
    "register_tools",
]