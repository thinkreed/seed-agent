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

重构说明：
- 会话管理移至 collaboration_tools_core/_session.py
- 多脑一手移至 collaboration_tools_core/_multi_brain_one_hand.py
- 一脑多手移至 collaboration_tools_core/_one_brain_multi_hand.py
- 消息传递移至 collaboration_tools_core/_message.py
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.collaboration_tools_core import (
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
    get_session_registry,
    get_orchestrator_registry,
)

if TYPE_CHECKING:
    from src.tools import ToolRegistry

logger = logging.getLogger(__name__)


def setup_multi_brain_multi_hand(
    session_id: str,
    pairs: list[dict[str, Any]] | None = None,
) -> str:
    """设置多脑多手编排器"""
    from src.client import LLMGateway
    from src.collaboration import InterAgentMessageBus, MultiBrainMultiHandOrchestrator
    from src.llm_client import LLMClient
    from src.sandbox import IsolationLevel, Sandbox

    sessions = get_session_registry()
    orchestrators = get_orchestrator_registry()

    if session_id not in sessions:
        return f"Error: Session {session_id} not found"

    session_data = sessions[session_id]
    session = session_data["session"]

    pairs = pairs or []
    if not pairs:
        return "Error: pairs required for multi_brain_multi_hand mode"

    agent_sandbox_pairs: list[tuple[LLMClient, Sandbox]] = []
    pair_ids: list[str] = []

    for pair_config in pairs:
        gateway_path = pair_config.get("gateway_path", "config/models.yaml")
        model_id = pair_config.get("model_id")

        if not model_id:
            return "Error: model_id required in each pair config"

        gateway = LLMGateway(gateway_path)
        llm_client = LLMClient(gateway, model_id)

        sandbox_cfg = pair_config.get("sandbox_config", {})
        sandbox = Sandbox(
            isolation_level=IsolationLevel(
                sandbox_cfg.get("isolation_level", "process")
            ),
            workspace_path=Path(sandbox_cfg.get("workspace_path"))
            if sandbox_cfg.get("workspace_path")
            else None,
        )

        agent_sandbox_pairs.append((llm_client, sandbox))
        pair_ids.append(str(hash(model_id) % 10000))

    message_bus = InterAgentMessageBus(session)
    message_bus.set_pair_ids(pair_ids)

    orchestrator = MultiBrainMultiHandOrchestrator(
        session=session,
        agent_sandbox_pairs=agent_sandbox_pairs,
        message_bus=message_bus,
    )

    orchestrators[session_id] = orchestrator
    # 注册消息总线
    from src.collaboration_tools_core._session import _message_buses
    _message_buses[session_id] = message_bus
    session_data["status"] = "ready"

    logger.info(f"MultiBrainMultiHand orchestrator set up: {session_id}")
    return f"Multi-brain multi-hand orchestrator set up:\nPairs: {len(agent_sandbox_pairs)}\nMessage bus: enabled\nStatus: ready"


def coordinated_task(
    session_id: str,
    task: str,
    enable_dynamic_assignment: bool = False,
) -> str:
    """协调任务（多脑多手模式）"""
    from src.collaboration import MultiBrainMultiHandOrchestrator
    from src.tools.utils import add_background_task

    orchestrators = get_orchestrator_registry()

    if session_id not in orchestrators:
        return f"Error: Orchestrator not set up for session {session_id}"

    orchestrator = orchestrators[session_id]

    if not isinstance(orchestrator, MultiBrainMultiHandOrchestrator):
        return "Error: Wrong orchestrator type for coordinated_task"

    try:
        asyncio.get_running_loop()
        if enable_dynamic_assignment:
            bg_task = asyncio.create_task(orchestrator.dynamic_task_assignment(task))
        else:
            bg_task = asyncio.create_task(orchestrator.coordinated_execution(task))
        add_background_task(bg_task)
        return f"Coordinated task started: {task[:100]}\nDynamic assignment: {enable_dynamic_assignment}"
    except RuntimeError:
        return "Task requires async context. Use in AgentLoop."


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
    # 会话管理
    "create_collaboration_session",
    "get_collaboration_status",
    "destroy_collaboration_session",
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