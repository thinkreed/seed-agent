"""
多脑一手模式工具

基于 Harness Engineering "多脑一手" 协作模式设计。
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.collaboration_tools_core._session import (
    _orchestrators,
    _session_lock,
    _collaboration_sessions,
)

if TYPE_CHECKING:
    from src.collaboration import MultiBrainOneHandOrchestrator

logger = logging.getLogger(__name__)


def setup_multi_brain_one_hand(
    session_id: str,
    sandbox_config: dict[str, Any] | None = None,
    brain_configs: list[dict[str, str]] | None = None,
    perspectives: list[str] | None = None,
) -> str:
    """设置多脑一手编排器"""
    from src.client import LLMGateway
    from src.collaboration import MultiBrainOneHandOrchestrator
    from src.llm_client import LLMClient
    from src.sandbox import IsolationLevel, Sandbox

    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

    sandbox_config = sandbox_config or {}
    fs_root = sandbox_config.get("file_system_root")
    ws_path = sandbox_config.get("workspace_path")
    sandbox = Sandbox(
        isolation_level=IsolationLevel(
            sandbox_config.get("isolation_level", "process")
        ),
        file_system_root=Path(fs_root) if isinstance(fs_root, (str, Path)) else None,
        workspace_path=Path(ws_path) if isinstance(ws_path, (str, Path)) else None,
    )

    brain_configs = brain_configs or []
    if not brain_configs:
        return "Error: brain_configs required for multi_brain_one_hand mode"

    llm_clients: list[LLMClient] = []
    for brain_cfg in brain_configs:
        gateway_path = brain_cfg.get("gateway_path", "config/models.yaml")
        model_id = brain_cfg.get("model_id")

        if not model_id:
            return "Error: model_id required in each brain_config"

        gateway = LLMGateway(gateway_path)
        client = LLMClient(gateway, model_id)
        llm_clients.append(client)

    orchestrator = MultiBrainOneHandOrchestrator(
        sandbox=sandbox,
        llm_clients=llm_clients,
        perspectives=perspectives,
    )

    with _session_lock:
        _orchestrators[session_id] = orchestrator
        _collaboration_sessions[session_id]["status"] = "ready"

    logger.info(f"MultiBrainOneHand orchestrator set up: {session_id}")
    return f"Multi-brain one-hand orchestrator set up:\nBrains: {len(llm_clients)}\nPerspectives: {perspectives or 'default'}\nStatus: ready"


def multi_angle_analysis(session_id: str, target: str) -> str:
    """多角度分析"""
    from src.collaboration import MultiBrainOneHandOrchestrator
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"
        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, MultiBrainOneHandOrchestrator):
        return "Error: Wrong orchestrator type for multi_angle_analysis"

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            _run_multi_angle_analysis_async(orchestrator, target)
        )
        add_background_task(task)
        return f"Multi-angle analysis started for: {target[:100]}\nUse 'get_collaboration_status' to check progress."
    except RuntimeError:
        return f"Analysis requires async context. Use in AgentLoop.\nTarget: {target[:100]}"


async def _run_multi_angle_analysis_async(
    orchestrator: "MultiBrainOneHandOrchestrator",
    target: str,
) -> dict[str, Any]:
    """异步执行多角度分析"""
    return await orchestrator.analyze_from_multiple_angles(target)


def collaborative_improve(session_id: str, target: str) -> str:
    """协作改进"""
    from src.collaboration import MultiBrainOneHandOrchestrator
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"
        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, MultiBrainOneHandOrchestrator):
        return "Error: Wrong orchestrator type for collaborative_improve"

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            _run_collaborative_improve_async(orchestrator, target)
        )
        add_background_task(task)
        return f"Collaborative improvement started for: {target[:100]}"
    except RuntimeError:
        return "Improvement requires async context. Use in AgentLoop."


async def _run_collaborative_improve_async(
    orchestrator: "MultiBrainOneHandOrchestrator",
    target: str,
) -> dict[str, Any]:
    """异步执行协作改进"""
    return await orchestrator.collaborative_improve(target)