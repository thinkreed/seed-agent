"""
协作工具核心类型和会话管理

包含会话管理工具和全局状态管理。
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 全局协作会话管理
_collaboration_sessions: dict[str, Any] = {}
_orchestrators: dict[str, Any] = {}
_message_buses: dict[str, Any] = {}

# 线程安全锁
_session_lock = threading.Lock()


def create_collaboration_session(
    session_id: str | None = None,
    mode: str = "multi_brain_one_hand",
    config: dict[str, Any] | None = None,
) -> str:
    """创建协作会话"""
    from src.collaboration import CollaborationMode
    from src.session_event_stream import SessionEventStream

    session_id = (
        session_id or f"collab_{int(asyncio.get_event_loop().time() * 1000) % 1000000}"
    )

    mode_map = {
        "multi_brain_one_hand": CollaborationMode.MULTI_BRAIN_ONE_HAND,
        "one_brain_multi_hand": CollaborationMode.ONE_BRAIN_MULTI_HAND,
        "multi_brain_multi_hand": CollaborationMode.MULTI_BRAIN_MULTI_HAND,
    }

    if mode not in mode_map:
        return f"Error: Unknown mode '{mode}'. Supported: multi_brain_one_hand, one_brain_multi_hand, multi_brain_multi_hand"

    config = config or {}

    with _session_lock:
        storage_path = config.get("storage_path")
        session = SessionEventStream(
            session_id=session_id,
            storage_path=Path(storage_path) if storage_path else None,
        )

        _collaboration_sessions[session_id] = {
            "session": session,
            "mode": mode,
            "config": config,
            "status": "initialized",
        }

    logger.info(f"Collaboration session created: {session_id}, mode={mode}")
    return f"Collaboration session created: {session_id}\nMode: {mode}\nStatus: initialized"


def get_collaboration_status(session_id: str) -> str:
    """获取协作状态"""
    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

        session_data = _collaboration_sessions[session_id]
        orchestrator = _orchestrators.get(session_id)
        message_bus = _message_buses.get(session_id)

    status_info = {
        "session_id": session_id,
        "mode": session_data["mode"],
        "status": session_data["status"],
        "session_events": session_data["session"].get_event_count(),
        "orchestrator": orchestrator is not None,
        "message_bus": message_bus is not None,
    }

    if orchestrator:
        mode = session_data["mode"]
        if mode == "multi_brain_one_hand":
            status_info["agents"] = orchestrator.get_agents_status()
        elif mode == "one_brain_multi_hand":
            status_info["sandboxes"] = orchestrator.get_sandboxes_status()
        elif mode == "multi_brain_multi_hand":
            status_info["pairs"] = orchestrator.get_pairs_status()

    if message_bus:
        status_info["message_count"] = message_bus.get_message_count()

    return f"Collaboration Status:\n{json.dumps(status_info, ensure_ascii=False, indent=2)}"


def destroy_collaboration_session(session_id: str) -> str:
    """销毁协作会话"""
    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

        _orchestrators.pop(session_id, None)
        _message_buses.pop(session_id, None)
        _collaboration_sessions.pop(session_id)

    logger.info(f"Collaboration session destroyed: {session_id}")
    return f"Collaboration session {session_id} destroyed and resources cleaned up."


# 导出全局状态（供其他模块使用）
def get_session_registry() -> dict[str, Any]:
    """获取会话注册表"""
    return _collaboration_sessions

def get_orchestrator_registry() -> dict[str, Any]:
    """获取编排器注册表"""
    return _orchestrators

def get_message_bus_registry() -> dict[str, Any]:
    """获取消息总线注册表"""
    return _message_buses