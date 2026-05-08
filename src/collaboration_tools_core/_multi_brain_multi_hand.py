"""多脑多手协作模式 - Multi-Brain Multi-Hand Orchestrator"""

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def setup_multi_brain_multi_hand(
    session_id: str,
    pairs: list[dict[str, Any]] | None = None,
) -> str:
    """设置多脑多手编排器"""
    from src.client import LLMGateway
    from src.collaboration import InterAgentMessageBus, MultiBrainMultiHandOrchestrator
    from src.collaboration_tools_core._session import (
        _message_buses,
        get_orchestrator_registry,
        get_session_registry,
    )
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
    from src.collaboration_tools_core._session import get_orchestrator_registry
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