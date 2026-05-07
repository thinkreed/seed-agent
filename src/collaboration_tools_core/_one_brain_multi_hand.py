"""
一脑多手模式工具

基于 Harness Engineering "一脑多手" 协作模式设计。
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.collaboration_tools_core._session import (
    _collaboration_sessions,
    _orchestrators,
    _session_lock,
)

if TYPE_CHECKING:
    from src.collaboration import OneBrainMultiHandOrchestrator

logger = logging.getLogger(__name__)


def setup_one_brain_multi_hand(
    session_id: str,
    brain_config: dict[str, str] | None = None,
    sandbox_configs: list[dict[str, Any]] | None = None,
    labels: list[str] | None = None,
) -> str:
    """设置一脑多手编排器"""
    from src.client import LLMGateway
    from src.collaboration import OneBrainMultiHandOrchestrator
    from src.llm_client import LLMClient

    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

    brain_config = brain_config or {}
    gateway_path = brain_config.get("gateway_path", "config/models.yaml")
    model_id = brain_config.get("model_id")

    if not model_id:
        return "Error: model_id required in brain_config"

    gateway = LLMGateway(gateway_path)
    llm_client = LLMClient(gateway, model_id)

    sandbox_configs = sandbox_configs or [{"isolation_level": "process"}]
    orchestrator = OneBrainMultiHandOrchestrator(
        llm_client=llm_client,
        sandbox_configs=sandbox_configs,
        labels=labels,
    )

    with _session_lock:
        _orchestrators[session_id] = orchestrator
        _collaboration_sessions[session_id]["status"] = "ready"

    logger.info(f"OneBrainMultiHand orchestrator set up: {session_id}")
    return f"One-brain multi-hand orchestrator set up:\nBrain: {model_id}\nSandboxes: {len(sandbox_configs)}\nLabels: {labels or 'default'}\nStatus: ready"


def cross_environment_execute(session_id: str, task: str) -> str:
    """跨环境执行"""
    from src.collaboration import OneBrainMultiHandOrchestrator
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"
        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, OneBrainMultiHandOrchestrator):
        return "Error: Wrong orchestrator type for cross_environment_execute"

    try:
        asyncio.get_running_loop()
        task_coro = asyncio.create_task(
            _run_cross_environment_async(orchestrator, task)
        )
        add_background_task(task_coro)
        return f"Cross-environment execution started: {task[:100]}"
    except RuntimeError:
        return "Execution requires async context. Use in AgentLoop."


async def _run_cross_environment_async(
    orchestrator: "OneBrainMultiHandOrchestrator",
    task: str,
) -> dict[str, Any]:
    """异步执行跨环境任务"""
    return await orchestrator.execute_in_multiple_environments(task)


def cross_environment_test(session_id: str, test_code: str) -> str:
    """跨环境测试"""
    from src.collaboration import OneBrainMultiHandOrchestrator
    from src.tools.utils import add_background_task

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"
        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, OneBrainMultiHandOrchestrator):
        return "Error: Wrong orchestrator type for cross_environment_test"

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(orchestrator.cross_environment_test(test_code))
        add_background_task(task)
        return "Cross-environment test started"
    except RuntimeError:
        return "Test requires async context. Use in AgentLoop."