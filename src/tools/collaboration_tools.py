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

版本: v2.0 (重写实现)
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.collaboration import (
        MultiBrainOneHandOrchestrator,
        OneBrainMultiHandOrchestrator,
    )

logger = logging.getLogger(__name__)

# 全局协作会话管理
_collaboration_sessions: dict[str, Any] = {}
_orchestrators: dict[str, Any] = {}
_message_buses: dict[str, Any] = {}

# 线程安全锁
_session_lock = threading.Lock()

# 后台任务集合
_background_tasks: set[asyncio.Task[Any]] = set()
_MAX_BACKGROUND_TASKS = 50


def _add_background_task(task: asyncio.Task[Any]) -> None:
    """安全添加后台任务"""
    if len(_background_tasks) >= _MAX_BACKGROUND_TASKS:
        done_tasks = [t for t in _background_tasks if t.done()]
        for t in done_tasks:
            _background_tasks.discard(t)
    _background_tasks.add(task)
    task.add_done_callback(lambda t: _background_tasks.discard(t))


# === 会话管理工具 ===


def create_collaboration_session(
    session_id: str | None = None,
    mode: str = "multi_brain_one_hand",
    config: dict[str, Any] | None = None,
) -> str:
    """创建协作会话

    Args:
        session_id: 会话 ID（可选，自动生成）
        mode: 协作模式 - 'multi_brain_one_hand', 'one_brain_multi_hand', 'multi_brain_multi_hand'
        config: 配置参数

    Returns:
        会话 ID 和创建状态
    """
    from src.collaboration import CollaborationMode
    from src.session_event_stream import SessionEventStream

    session_id = (
        session_id or f"collab_{int(asyncio.get_event_loop().time() * 1000) % 1000000}"
    )

    # 验证模式
    mode_map = {
        "multi_brain_one_hand": CollaborationMode.MULTI_BRAIN_ONE_HAND,
        "one_brain_multi_hand": CollaborationMode.ONE_BRAIN_MULTI_HAND,
        "multi_brain_multi_hand": CollaborationMode.MULTI_BRAIN_MULTI_HAND,
    }

    if mode not in mode_map:
        return f"Error: Unknown mode '{mode}'. Supported: multi_brain_one_hand, one_brain_multi_hand, multi_brain_multi_hand"

    config = config or {}

    with _session_lock:
        # 创建 SessionEventStream
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
    """获取协作状态

    Args:
        session_id: 会话 ID

    Returns:
        状态信息
    """
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
        # 获取编排器状态
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
    """销毁协作会话

    Args:
        session_id: 会话 ID

    Returns:
        操作结果
    """
    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

        # 清理资源
        _orchestrators.pop(session_id, None)
        _message_buses.pop(session_id, None)
        _collaboration_sessions.pop(session_id)

    logger.info(f"Collaboration session destroyed: {session_id}")
    return f"Collaboration session {session_id} destroyed and resources cleaned up."


# === 多脑一手模式工具 ===


def setup_multi_brain_one_hand(
    session_id: str,
    sandbox_config: dict[str, Any] | None = None,
    brain_configs: list[dict[str, str]] | None = None,
    perspectives: list[str] | None = None,
) -> str:
    """设置多脑一手编排器

    Args:
        session_id: 会话 ID
        sandbox_config: Sandbox 配置
        brain_configs: 大脑配置列表（每个包含 gateway_path 和 model_id）
        perspectives: 分析视角列表

    Returns:
        设置结果
    """
    from src.client import LLMGateway
    from src.collaboration import MultiBrainOneHandOrchestrator
    from src.llm_client import LLMClient
    from src.sandbox import IsolationLevel, Sandbox

    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

        _collaboration_sessions[session_id]

    # 创建 Sandbox
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

    # 创建 LLMClient
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

    # 创建编排器
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


def multi_angle_analysis(
    session_id: str,
    target: str,
) -> str:
    """多角度分析（多脑一手模式）

    Args:
        session_id: 会话 ID
        target: 分析目标（文件路径或代码片段）

    Returns:
        分析结果
    """
    from src.collaboration import MultiBrainOneHandOrchestrator

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"

        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, MultiBrainOneHandOrchestrator):
        return "Error: Wrong orchestrator type for multi_angle_analysis"

    # 尝试异步执行
    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            _run_multi_angle_analysis_async(orchestrator, target)
        )
        _add_background_task(task)
        return f"Multi-angle analysis started for: {target[:100]}\nUse 'get_collaboration_status' to check progress."
    except RuntimeError:
        # 没有事件循环，需要同步执行（但实际是异步的）
        return f"Analysis requires async context. Use in AgentLoop.\nTarget: {target[:100]}"


async def _run_multi_angle_analysis_async(
    orchestrator: "MultiBrainOneHandOrchestrator",
    target: str,
) -> dict[str, Any]:
    """异步执行多角度分析"""
    return await orchestrator.analyze_from_multiple_angles(target)


def collaborative_improve(
    session_id: str,
    target: str,
) -> str:
    """协作改进（多脑一手模式）

    Args:
        session_id: 会话 ID
        target: 改进目标

    Returns:
        改进建议
    """
    from src.collaboration import MultiBrainOneHandOrchestrator

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
        _add_background_task(task)
        return f"Collaborative improvement started for: {target[:100]}"
    except RuntimeError:
        return "Improvement requires async context. Use in AgentLoop."


async def _run_collaborative_improve_async(
    orchestrator: "MultiBrainOneHandOrchestrator",
    target: str,
) -> dict[str, Any]:
    """异步执行协作改进"""
    return await orchestrator.collaborative_improve(target)


# === 一脑多手模式工具 ===


def setup_one_brain_multi_hand(
    session_id: str,
    brain_config: dict[str, str] | None = None,
    sandbox_configs: list[dict[str, Any]] | None = None,
    labels: list[str] | None = None,
) -> str:
    """设置一脑多手编排器

    Args:
        session_id: 会话 ID
        brain_config: 大脑配置（包含 gateway_path 和 model_id）
        sandbox_configs: 多个 Sandbox 配置列表
        labels: 工作台标签（如 ["python_env", "node_env"]）

    Returns:
        设置结果
    """
    from src.client import LLMGateway
    from src.collaboration import OneBrainMultiHandOrchestrator
    from src.llm_client import LLMClient

    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

    # 创建 LLMClient
    brain_config = brain_config or {}
    gateway_path = brain_config.get("gateway_path", "config/models.yaml")
    model_id = brain_config.get("model_id")

    if not model_id:
        return "Error: model_id required in brain_config"

    gateway = LLMGateway(gateway_path)
    llm_client = LLMClient(gateway, model_id)

    # 创建编排器
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


def cross_environment_execute(
    session_id: str,
    task: str,
) -> str:
    """跨环境执行（一脑多手模式）

    Args:
        session_id: 会话 ID
        task: 任务描述

    Returns:
        执行状态
    """
    from src.collaboration import OneBrainMultiHandOrchestrator

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
        _add_background_task(task_coro)
        return f"Cross-environment execution started: {task[:100]}"
    except RuntimeError:
        return "Execution requires async context. Use in AgentLoop."


async def _run_cross_environment_async(
    orchestrator: "OneBrainMultiHandOrchestrator",
    task: str,
) -> dict[str, Any]:
    """异步执行跨环境任务"""
    return await orchestrator.execute_in_multiple_environments(task)


def cross_environment_test(
    session_id: str,
    test_code: str,
) -> str:
    """跨环境测试

    Args:
        session_id: 会话 ID
        test_code: 测试代码

    Returns:
        测试状态
    """
    from src.collaboration import OneBrainMultiHandOrchestrator

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"

        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, OneBrainMultiHandOrchestrator):
        return "Error: Wrong orchestrator type for cross_environment_test"

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(orchestrator.cross_environment_test(test_code))
        _add_background_task(task)
        return "Cross-environment test started"
    except RuntimeError:
        return "Test requires async context. Use in AgentLoop."


# === 多脑多手模式工具 ===


def setup_multi_brain_multi_hand(
    session_id: str,
    pairs: list[dict[str, Any]] | None = None,
) -> str:
    """设置多脑多手编排器

    Args:
        session_id: 会话 ID
        pairs: Claude + Sandbox 组合配置列表
            每个包含: gateway_path, model_id, sandbox_config

    Returns:
        设置结果
    """
    from src.client import LLMGateway
    from src.collaboration import InterAgentMessageBus, MultiBrainMultiHandOrchestrator
    from src.llm_client import LLMClient
    from src.sandbox import IsolationLevel, Sandbox

    with _session_lock:
        if session_id not in _collaboration_sessions:
            return f"Error: Session {session_id} not found"

        session_data = _collaboration_sessions[session_id]
        session = session_data["session"]

    # 创建组合
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

    # 创建消息总线
    message_bus = InterAgentMessageBus(session)
    message_bus.set_pair_ids(pair_ids)

    # 创建编排器
    orchestrator = MultiBrainMultiHandOrchestrator(
        session=session,
        agent_sandbox_pairs=agent_sandbox_pairs,
        message_bus=message_bus,
    )

    with _session_lock:
        _orchestrators[session_id] = orchestrator
        _message_buses[session_id] = message_bus
        _collaboration_sessions[session_id]["status"] = "ready"

    logger.info(f"MultiBrainMultiHand orchestrator set up: {session_id}")
    return f"Multi-brain multi-hand orchestrator set up:\nPairs: {len(agent_sandbox_pairs)}\nMessage bus: enabled\nStatus: ready"


def coordinated_task(
    session_id: str,
    task: str,
    enable_dynamic_assignment: bool = False,
) -> str:
    """协调任务（多脑多手模式）

    Args:
        session_id: 会话 ID
        task: 任务描述
        enable_dynamic_assignment: 是否启用动态任务分配

    Returns:
        执行状态
    """
    from src.collaboration import MultiBrainMultiHandOrchestrator

    with _session_lock:
        if session_id not in _orchestrators:
            return f"Error: Orchestrator not set up for session {session_id}"

        orchestrator = _orchestrators[session_id]

    if not isinstance(orchestrator, MultiBrainMultiHandOrchestrator):
        return "Error: Wrong orchestrator type for coordinated_task"

    try:
        asyncio.get_running_loop()
        if enable_dynamic_assignment:
            bg_task: asyncio.Task[Any] = asyncio.create_task(
                orchestrator.dynamic_task_assignment(task)
            )
        else:
            bg_task = asyncio.create_task(orchestrator.coordinated_execution(task))
        _add_background_task(bg_task)
        return f"Coordinated task started: {task[:100]}\nDynamic assignment: {enable_dynamic_assignment}"
    except RuntimeError:
        return "Task requires async context. Use in AgentLoop."


# === 消息传递工具 ===


def send_agent_message(
    session_id: str,
    from_agent: str,
    to_agent: str,
    message_type: str,
    content: dict[str, Any],
) -> str:
    """发送智能体消息

    Args:
        session_id: 会话 ID
        from_agent: 发送方 ID
        to_agent: 接收方 ID
        message_type: 消息类型
        content: 消息内容

    Returns:
        发送结果
    """

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"

        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.send_message(from_agent, to_agent, message_type, content)
        )
        _add_background_task(task)
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
    """广播消息

    Args:
        session_id: 会话 ID
        from_agent: 发送方 ID
        message_type: 消息类型
        content: 消息内容
        exclude_self: 是否排除自己

    Returns:
        广播结果
    """

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"

        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.broadcast(from_agent, message_type, content, exclude_self)
        )
        _add_background_task(task)
        return f"Message broadcast from: {from_agent}\nType: {message_type}"
    except RuntimeError:
        return "Broadcast requires async context. Use in AgentLoop."


def receive_agent_messages(
    session_id: str,
    agent_id: str,
    message_types: list[str] | None = None,
) -> str:
    """接收智能体消息

    Args:
        session_id: 会话 ID
        agent_id: 接收方 ID
        message_types: 过滤的消息类型（可选）

    Returns:
        消息列表
    """

    with _session_lock:
        if session_id not in _message_buses:
            return f"Error: Message bus not set up for session {session_id}"

        message_bus = _message_buses[session_id]

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(
            message_bus.receive_messages(agent_id, message_types)
        )
        _add_background_task(task)
        return f"Message receiving started for agent: {agent_id}"
    except RuntimeError:
        # 同步获取消息数量
        count = message_bus.get_message_count()
        return f"Messages available: {count}. Use async context for full retrieval."


def register_message_handler(
    session_id: str,
    message_type: str,
    handler_name: str,
) -> str:
    """注册消息处理器

    Args:
        session_id: 会话 ID
        message_type: 消息类型
        handler_name: 预定义处理器名称（不再支持自定义代码）

    Returns:
        注册结果

    Security Note:
        已移除 eval 方案，改为预定义处理器注册机制。
        可用处理器：
        - "log": 打印消息日志
        - "count": 统计消息数量
        - "echo": 返回消息内容
    """
    # 预定义处理器（安全替代 eval 方案）
    predefined_handlers: dict[str, Callable[[dict], None]] = {
        "log": lambda msg: logger.info(
            f"Message received: {msg.get('type', 'unknown')} - {msg.get('content', '')[:100]}"
        ),
        "count": lambda msg: None,  # 仅计数，由 message_bus 内部实现
        "echo": lambda msg: print(
            f"[Message] {msg.get('type', 'unknown')}: {msg.get('content', '')}"
        ),
    }

    if handler_name not in predefined_handlers:
        available = list(predefined_handlers.keys())
        return (
            f"Error: Unknown handler '{handler_name}'. Available handlers: {available}"
        )

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


# === 工具注册 ===


def register_tools(registry: Any) -> None:
    """注册所有协作工具到 Registry

    Args:
        registry: 工具注册表
    """
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
