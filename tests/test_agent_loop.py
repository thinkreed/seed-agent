"""
Tests for src/agent_loop.py - 纯三件套架构 + 上下文工程

基于 Harness Engineering "三件套解耦架构" 设计：
- AgentLoop 强制使用 Harness/Sandbox/LLMClient
- 无 legacy 代码，移除向后兼容测试
- Session 不可变事件流测试保留

上下文工程优化：
- 渐进式压缩：三层压缩策略
- 智能裁剪：任务相关性过滤
- 原始数据不丢失：Session 保留完整历史

Coverage targets:
- 三件套架构初始化
- 上下文工程初始化
- SessionEventStream integration
- run() 方法 (使用 Harness)
- stream_run() 方法 (使用 Harness)
- Summary marker mechanism
- Skill outcome recording
- State recovery and replay
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent_loop import AgentLoop
from harness import MaxIterationsExceeded
from session_event_stream import SessionEventStream, EventType
from sandbox import IsolationLevel
from request_queue import RequestPriority
from context_engineering import CompressionConfig, PruningConfig


# ==================== Fixtures ====================

@pytest.fixture
def temp_storage_path():
    """临时事件存储路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_gateway():
    """Mock LLMGateway instance."""
    gateway = MagicMock()
    gateway.config = MagicMock()
    gateway.config.agents = MagicMock()
    gateway.config.agents['defaults'] = MagicMock()
    gateway.config.agents['defaults'].defaults = MagicMock()
    gateway.config.agents['defaults'].defaults.primary = "openai/gpt-4o"
    gateway.config.models = {}

    # Mock model config
    mock_model = MagicMock()
    mock_model.id = "gpt-4o"
    mock_model.contextWindow = 128000
    mock_model.maxOutputTokens = 4096
    mock_provider = MagicMock()
    mock_provider.models = [mock_model]
    gateway.config.models = {"openai": mock_provider}

    gateway.chat_completion = AsyncMock(return_value={
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': 'Response text'
            }
        }]
    })
    gateway.get_model_config = MagicMock(return_value=mock_model)
    gateway.get_active_provider = AsyncMock(return_value="openai")
    gateway.get_rate_limit_status = MagicMock(return_value=None)

    return gateway


def full_agent_patches(session_id='test_session', storage_path=None):
    """Full set of patches for AgentLoop initialization."""
    def noop(*args, **kwargs):
        pass

    def mock_init(*args, **kwargs):
        pass

    mock_skill_loader = MagicMock()
    mock_skill_loader.return_value.get_skills_prompt.return_value = "\n## Available Skills\n- test-skill"

    patches = [
        patch('agent_loop.ToolRegistry', return_value=MagicMock()),
        patch('agent_loop.SkillLoader', mock_skill_loader),
        patch('agent_loop.TaskScheduler', return_value=MagicMock()),
        patch('agent_loop.SubagentManager', return_value=MagicMock()),
        patch('tools.subagent_tools.init_subagent_manager', mock_init),
        patch('tools.builtin_tools.register_builtin_tools', noop),
        patch('tools.memory_tools.register_memory_tools', noop),
        patch('tools.skill_loader.register_skill_tools', noop),
        patch('scheduler.register_scheduler_tools', noop),
        patch('tools.ralph_tools.register_ralph_tools', noop),
        patch('tools.subagent_tools.register_subagent_tools', noop),
        patch('tools.collaboration_tools.register_tools', noop),
        patch('agent_loop._generate_session_filename', return_value=session_id),
        patch('tiktoken.encoding_for_model', side_effect=KeyError),
        patch('tiktoken.get_encoding', return_value=MagicMock()),
    ]

    if storage_path:
        patches.append(
            patch('session_event_stream.DEFAULT_STORAGE_PATH', storage_path)
        )

    return patches


class _PatchManager:
    """Context manager for multiple patches."""
    def __init__(self, patches):
        self._patches = patches
        self._entered = []

    def __enter__(self):
        for p in self._patches:
            self._entered.append(p.__enter__)
            p.__enter__()
        return self

    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.__exit__(*args)


def create_agent(gateway, model_id="openai/gpt-4o", session_id='test_session',
                 storage_path=None, **kwargs):
    """Helper to create AgentLoop with all patches applied."""
    patches = full_agent_patches(session_id, storage_path)
    mgr = _PatchManager(patches)
    mgr.__enter__()
    try:
        agent = AgentLoop(gateway=gateway, model_id=model_id, **kwargs)
        return agent, mgr
    except:
        mgr.__exit__(None, None, None)
        raise


@pytest.fixture
def agent_loop_instance(mock_gateway, temp_storage_path):
    """Create an AgentLoop instance with mocked dependencies."""
    agent, mgr = create_agent(
        mock_gateway,
        session_id='test_session_123',
        storage_path=temp_storage_path
    )
    agent._patch_manager = mgr
    yield agent
    mgr.__exit__(None, None, None)


# ==================== Initialization Tests ====================

class TestAgentLoopInit:
    """Test AgentLoop initialization - 三件套架构."""

    def test_init_default_values(self, agent_loop_instance, mock_gateway):
        """Test initialization with default values."""
        agent = agent_loop_instance
        assert agent.gateway == mock_gateway
        assert agent.model_id == "openai/gpt-4o"
        assert agent.max_iterations == 100
        assert agent.summary_interval == 10
        assert agent._conversation_rounds == 0
        assert agent.session_id == 'test_session_123'

        # 验证三件套初始化
        assert agent.llm_client is not None
        assert agent.harness is not None
        assert agent.sandbox is not None
        assert agent.session is not None

    def test_init_custom_isolation_level(self, mock_gateway, temp_storage_path):
        """Test initialization with custom isolation level."""
        agent, mgr = create_agent(
            mock_gateway,
            isolation_level=IsolationLevel.CONTAINER,
            storage_path=temp_storage_path
        )
        try:
            assert agent.sandbox.isolation_level == IsolationLevel.CONTAINER
        finally:
            mgr.__exit__(None, None, None)

    def test_session_start_event_recorded(self, agent_loop_instance):
        """Test session start event is recorded."""
        agent = agent_loop_instance
        events = agent.session.get_events()
        assert len(events) >= 1
        assert events[0]["type"] == EventType.SESSION_START.value


# ==================== 三件套架构 Tests ====================

class TestTrioArchitecture:
    """Test 三件套架构集成."""

    def test_llm_client_initialized(self, agent_loop_instance):
        """Test LLMClient (大脑) 初始化."""
        agent = agent_loop_instance
        assert agent.llm_client is not None
        assert agent.llm_client.model_id == agent.model_id

    def test_sandbox_initialized(self, agent_loop_instance):
        """Test Sandbox (工作台) 初始化."""
        agent = agent_loop_instance
        assert agent.sandbox is not None
        assert agent.sandbox.isolation_level == IsolationLevel.PROCESS

    def test_harness_initialized(self, agent_loop_instance):
        """Test Harness (控制器) 初始化."""
        agent = agent_loop_instance
        assert agent.harness is not None
        assert agent.harness.llm_client == agent.llm_client
        assert agent.harness.session == agent.session
        assert agent.harness.sandbox == agent.sandbox

    def test_tools_registered_in_sandbox(self, agent_loop_instance):
        """Test tools registered in sandbox."""
        agent = agent_loop_instance
        assert agent.sandbox._tools is not None
        assert agent.sandbox._tools == agent.tools

    def test_context_engineering_initialized(self, agent_loop_instance):
        """Test ContextEngineering 初始化."""
        agent = agent_loop_instance
        assert agent._context_engineering is not None
        assert agent.harness._context_engineering is not None


# ==================== 上下文工程 Tests ====================

class TestContextEngineeringIntegration:
    """Test 上下文工程集成."""

    def test_default_pruning_enabled(self, agent_loop_instance):
        """Test default pruning is enabled."""
        agent = agent_loop_instance
        assert agent._enable_pruning is True

    def test_custom_compression_config(self, mock_gateway, temp_storage_path):
        """Test custom compression configuration."""
        custom_config = CompressionConfig()
        custom_config.max_context_messages = 30

        agent, mgr = create_agent(
            mock_gateway,
            storage_path=temp_storage_path,
            compression_config=custom_config
        )

        try:
            assert agent._compression_config is not None
            assert agent._compression_config.max_context_messages == 30
        finally:
            mgr.__exit__(None, None, None)

    def test_custom_pruning_config(self, mock_gateway, temp_storage_path):
        """Test custom pruning configuration."""
        custom_config = PruningConfig()
        custom_config.relevance_threshold = 0.5

        agent, mgr = create_agent(
            mock_gateway,
            storage_path=temp_storage_path,
            pruning_config=custom_config
        )

        try:
            assert agent._pruning_config is not None
            assert agent._pruning_config.relevance_threshold == 0.5
        finally:
            mgr.__exit__(None, None, None)

    def test_disable_pruning(self, mock_gateway, temp_storage_path):
        """Test disabling pruning."""
        agent, mgr = create_agent(
            mock_gateway,
            storage_path=temp_storage_path,
            enable_pruning=False
        )

        try:
            assert agent._enable_pruning is False
            assert agent.harness._enable_pruning is False
        finally:
            mgr.__exit__(None, None, None)


# ==================== Run Tests ====================

class TestRunMethods:
    """Test run() and stream_run() methods - 使用 Harness."""

    @pytest.mark.asyncio
    async def test_run_basic(self, agent_loop_instance):
        """Test basic run() using Harness."""
        agent = agent_loop_instance
        agent.harness.run_conversation = AsyncMock(
            return_value={"status": "completed", "content": "Response text"}
        )

        result = await agent.run("hello")

        assert result == "Response text"
        agent.harness.run_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_with_custom_priority(self, agent_loop_instance):
        """Test run() with custom priority."""
        agent = agent_loop_instance
        agent.harness.run_conversation = AsyncMock(
            return_value={"status": "completed", "content": "Response"}
        )

        result = await agent.run("hello", priority=RequestPriority.NORMAL)

        assert result == "Response"
        agent.harness.run_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_max_iterations_exceeded(self, agent_loop_instance):
        """Test run() with MaxIterationsExceeded."""
        agent = agent_loop_instance
        agent.harness.run_conversation = AsyncMock(
            side_effect=MaxIterationsExceeded(30)
        )

        with pytest.raises(MaxIterationsExceeded):
            await agent.run("hello")

        # 验证 session end 事件被记录
        events = agent.session.get_events()
        end_events = [e for e in events if e["type"] == EventType.SESSION_END.value]
        assert len(end_events) >= 1

    @pytest.mark.asyncio
    async def test_stream_run_basic(self, agent_loop_instance):
        """Test basic stream_run() uses Harness.stream_conversation() for true streaming."""
        agent = agent_loop_instance

        # Mock stream_conversation to yield real chunks
        async def mock_stream_conversation(prompt, priority, signal):
            yield {"type": "chunk", "content": "Hello"}
            yield {"type": "chunk", "content": " world"}
            yield {"type": "final", "content": "Hello world"}

        agent.harness.stream_conversation = mock_stream_conversation

        chunks = []
        async for chunk in agent.stream_run("test"):
            chunks.append(chunk)

        # stream_run now yields multiple chunks (true streaming)
        assert len(chunks) >= 2
        assert chunks[-1]["type"] == "final"

        # Verify intermediate chunks are forwarded
        chunk_contents = [c["content"] for c in chunks if c["type"] == "chunk"]
        assert len(chunk_contents) >= 1

    @pytest.mark.asyncio
    async def test_stream_run_with_ask_user(self, agent_loop_instance):
        """Test stream_run() handles Ask User waiting correctly."""
        agent = agent_loop_instance

        # Mock stream_conversation that yields awaiting_user_input
        async def mock_stream_conversation(prompt, priority, signal):
            yield {"type": "chunk", "content": "Thinking..."}
            yield {"type": "awaiting_user_input", "request": {"request_id": "test-123", "questions": []}}

        agent.harness.stream_conversation = mock_stream_conversation

        # Mock stream_resume_with_user_response
        async def mock_stream_resume(response, priority, signal):
            yield {"type": "chunk", "content": "Continued..."}
            yield {"type": "final", "content": "Done"}

        agent.harness.stream_resume_with_user_response = mock_stream_resume

        # Collect chunks (will stop at awaiting_user_input since no response injected)
        chunks = []
        async for chunk in agent.stream_run("test"):
            chunks.append(chunk)
            if chunk["type"] == "awaiting_user_input":
                break  # Stop here to avoid blocking on wait

        # Verify awaiting_user_input chunk is yielded
        assert len(chunks) >= 1
        awaiting_chunks = [c for c in chunks if c["type"] == "awaiting_user_input"]
        assert len(awaiting_chunks) == 1

    @pytest.mark.asyncio
    async def test_stream_run_with_cancelled(self, agent_loop_instance):
        """Test stream_run() handles cancellation correctly."""
        agent = agent_loop_instance

        # Mock stream_conversation that yields cancelled
        async def mock_stream_conversation(prompt, priority, signal):
            yield {"type": "chunk", "content": "Partial..."}
            yield {"type": "cancelled", "reason": "user_interrupt"}

        agent.harness.stream_conversation = mock_stream_conversation

        chunks = []
        async for chunk in agent.stream_run("test"):
            chunks.append(chunk)

        # Verify cancelled chunk is yielded
        cancelled_chunks = [c for c in chunks if c["type"] == "cancelled"]
        assert len(cancelled_chunks) == 1
        assert cancelled_chunks[0]["reason"] == "user_interrupt"

    @pytest.mark.asyncio
    async def test_stream_run_with_error(self, agent_loop_instance):
        """Test stream_run() handles errors correctly."""
        agent = agent_loop_instance

        # Mock stream_conversation that yields error
        async def mock_stream_conversation(prompt, priority, signal):
            yield {"type": "chunk", "content": "Started..."}
            yield {"type": "error", "content": "Something went wrong"}

        agent.harness.stream_conversation = mock_stream_conversation

        chunks = []
        async for chunk in agent.stream_run("test"):
            chunks.append(chunk)

        # Verify error chunk is yielded
        error_chunks = [c for c in chunks if c["type"] == "error"]
        assert len(error_chunks) == 1


# ==================== Summary Tests ====================

class TestSummaryMechanism:
    """Test 摘要标记机制 (不截断历史)."""

    def test_create_summary_marker(self, agent_loop_instance):
        """Test summary marker creation."""
        agent = agent_loop_instance
        for i in range(5):
            agent.session.emit_event(EventType.USER_INPUT, {"content": f"msg{i}"})

        marker_id = agent.session.create_summary_marker(5, "Summary of 5 messages")

        assert marker_id >= 1
        all_events = agent.session.get_events()
        assert len(all_events) >= 6  # 5 input + 1 summary marker

    def test_find_last_summary_marker(self, agent_loop_instance):
        """Test finding last summary marker."""
        agent = agent_loop_instance
        agent.session._events.clear()
        agent.session._event_counter = 0

        agent.session.emit_event(EventType.USER_INPUT, {"content": "msg1"})
        agent.session.create_summary_marker(1, "First summary")
        agent.session.emit_event(EventType.USER_INPUT, {"content": "msg2"})
        agent.session.create_summary_marker(2, "Second summary")

        last_marker = agent.session.find_last_summary_marker()
        assert last_marker is not None
        assert last_marker["data"]["summary"] == "Second summary"

    def test_summary_does_not_truncate_history(self, agent_loop_instance):
        """Test summary marker does not truncate history."""
        agent = agent_loop_instance
        agent.session._events.clear()
        agent.session._event_counter = 0

        for i in range(10):
            agent.session.emit_event(EventType.USER_INPUT, {"content": f"msg{i}"})

        original_count = agent.session.get_event_count()
        agent.session.create_summary_marker(10, "Summary of all")

        new_count = agent.session.get_event_count()
        assert new_count == original_count + 1


# ==================== State Replay Tests ====================

class TestStateReplay:
    """Test 状态重放能力."""

    def test_replay_to_state(self, agent_loop_instance):
        """Test replaying events to state."""
        agent = agent_loop_instance
        agent.session._events.clear()
        agent.session._event_counter = 0

        agent.session.emit_event(EventType.USER_INPUT, {"content": "Hello"})
        agent.session.emit_event(EventType.LLM_RESPONSE, {"content": "Hi"})
        agent.session.emit_event(EventType.USER_INPUT, {"content": "Bye"})

        state = agent.session.replay_to_state(2)

        assert "messages" in state
        assert len(state["messages"]) >= 2

    def test_get_current_state(self, agent_loop_instance):
        """Test getting current state."""
        agent = agent_loop_instance
        agent.session.emit_event(EventType.USER_INPUT, {"content": "Test"})

        state = agent.get_current_state()

        assert "messages" in state
        assert "conversation_rounds" in state

    def test_get_event_count(self, agent_loop_instance):
        """Test getting event count."""
        agent = agent_loop_instance
        agent.session.emit_event(EventType.USER_INPUT, {"content": "Test"})

        count = agent.get_event_count()
        assert count >= 1


# ==================== Status Tests ====================

class TestStatusMethods:
    """Test status and helper methods."""

    def test_get_status(self, agent_loop_instance):
        """Test get_status returns complete info."""
        agent = agent_loop_instance

        status = agent.get_status()

        assert "session_id" in status
        assert "model_id" in status
        assert "event_count" in status
        assert "conversation_rounds" in status
        assert "context_window" in status
        assert "isolation_level" in status
        assert "harness_status" in status
        assert "context_engineering" in status
        assert "enabled" in status["context_engineering"]
        assert "pruning_enabled" in status["context_engineering"]

    def test_history_property(self, agent_loop_instance):
        """Test history property returns messages from event stream."""
        agent = agent_loop_instance
        agent.session.emit_event(EventType.USER_INPUT, {"content": "Test"})

        history = agent.history

        assert isinstance(history, list)


# ==================== Skill Outcome Tests ====================

class TestSkillOutcome:
    """Test skill outcome recording."""

    @patch('agent_loop._record_skill_outcome')
    def test_evaluate_skill_outcome_success(self, mock_record, agent_loop_instance):
        """Test successful skill outcome recording."""
        agent = agent_loop_instance
        agent._pending_skill_outcomes = [
            {
                'skill_name': 'test-skill',
                'result': 'Success output',
                'signals': ['test', 'signal'],
                'failed': False
            }
        ]

        agent._evaluate_and_record_skill_outcomes(final_success=True)

        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs['skill_name'] == 'test-skill'
        assert call_kwargs['outcome'] == 'success'
        assert call_kwargs['score'] == 1.0
        assert len(agent._pending_skill_outcomes) == 0

    @patch('agent_loop._record_skill_outcome')
    def test_evaluate_skill_outcome_failed(self, mock_record, agent_loop_instance):
        """Test failed skill outcome recording."""
        agent = agent_loop_instance
        agent._pending_skill_outcomes = [
            {
                'skill_name': 'failing-skill',
                'result': 'Error: not found',
                'signals': ['test'],
                'failed': True
            }
        ]

        agent._evaluate_and_record_skill_outcomes(final_success=True)

        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs['outcome'] == 'failed'
        assert call_kwargs['score'] == 0.0


# ==================== Event Stream Tests ====================

class TestEventStreamIntegration:
    """Test Session 不可变事件流集成."""

    def test_emit_user_input_event(self, temp_storage_path):
        """Test user input event recording."""
        stream = SessionEventStream("user_input_test", storage_path=temp_storage_path)
        event_id = stream.emit_event(
            EventType.USER_INPUT,
            {"content": "Hello"}
        )

        assert event_id >= 1
        events = stream.get_events(event_types=[EventType.USER_INPUT])
        assert len(events) == 1
        assert events[0]["data"]["content"] == "Hello"

    def test_emit_llm_response_event(self, temp_storage_path):
        """Test LLM response event recording."""
        stream = SessionEventStream("llm_response_test", storage_path=temp_storage_path)
        stream.emit_event(
            EventType.LLM_RESPONSE,
            {"content": "Hi there", "tool_calls": None}
        )

        events = stream.get_events(event_types=[EventType.LLM_RESPONSE])
        assert len(events) == 1
        assert events[0]["data"]["content"] == "Hi there"

    def test_emit_tool_result_event(self, temp_storage_path):
        """Test tool result event recording."""
        stream = SessionEventStream("tool_result_test", storage_path=temp_storage_path)
        stream.emit_event(
            EventType.TOOL_RESULT,
            {"tool_call_id": "call_123", "content": "File content"}
        )

        events = stream.get_events(event_types=[EventType.TOOL_RESULT])
        assert len(events) == 1
        assert events[0]["data"]["tool_call_id"] == "call_123"

    def test_get_events_range(self, agent_loop_instance):
        """Test event range query."""
        agent = agent_loop_instance
        agent.session._events.clear()
        agent.session._event_counter = 0

        for i in range(5):
            agent.session.emit_event(EventType.USER_INPUT, {"content": f"msg{i}"})

        events = agent.session.get_events(start_id=1, end_id=3)
        assert len(events) == 3
        assert events[0]["id"] == 1
        assert events[-1]["id"] == 3

    def test_get_events_by_type(self, agent_loop_instance):
        """Test event type filtering."""
        agent = agent_loop_instance
        agent.session._events.clear()
        agent.session._event_counter = 0

        agent.session.emit_event(EventType.USER_INPUT, {"content": "hello"})
        agent.session.emit_event(EventType.LLM_RESPONSE, {"content": "hi"})
        agent.session.emit_event(EventType.USER_INPUT, {"content": "bye"})

        user_events = agent.session.get_events(event_types=[EventType.USER_INPUT])
        assert len(user_events) == 2

        llm_events = agent.session.get_events(event_types=[EventType.LLM_RESPONSE])
        assert len(llm_events) == 1


# ==================== SecureSandbox Tests ====================

class TestSecureSandboxIntegration:
    """Test SecureSandbox 集成."""

    def test_default_secure_sandbox_enabled(self, mock_gateway, temp_storage_path):
        """Test SecureSandbox is enabled by default."""
        patches = full_agent_patches('test_secure', temp_storage_path)
        patches.append(
            patch('agent_loop.SecureSandbox', return_value=MagicMock(isolation_level=IsolationLevel.PROCESS))
        )
        mgr = _PatchManager(patches)
        mgr.__enter__()
        try:
            agent = AgentLoop(gateway=mock_gateway)
            assert agent._enable_secure_sandbox is True
            # SecureSandbox should be used
        finally:
            mgr.__exit__(None, None, None)

    def test_disable_secure_sandbox(self, mock_gateway, temp_storage_path):
        """Test disabling SecureSandbox uses regular Sandbox."""
        patches = full_agent_patches('test_no_secure', temp_storage_path)
        mgr = _PatchManager(patches)
        mgr.__enter__()
        try:
            agent = AgentLoop(gateway=mock_gateway, enable_secure_sandbox=False)
            assert agent._enable_secure_sandbox is False
            # Regular Sandbox should be used
        finally:
            mgr.__exit__(None, None, None)

    def test_custom_user_permission_level(self, mock_gateway, temp_storage_path):
        """Test custom user permission level."""
        patches = full_agent_patches('test_perm', temp_storage_path)
        patches.append(
            patch('agent_loop.SecureSandbox', return_value=MagicMock(isolation_level=IsolationLevel.PROCESS))
        )
        mgr = _PatchManager(patches)
        mgr.__enter__()
        try:
            agent = AgentLoop(gateway=mock_gateway, user_permission_level="admin")
            assert agent._user_permission_level == "admin"
        finally:
            mgr.__exit__(None, None, None)


# ==================== Collaboration Tools Tests ====================

class TestCollaborationToolsRegistration:
    """Test collaboration tools 注册."""

    def test_collaboration_tools_registered(self, agent_loop_instance):
        """Test collaboration tools are registered in tool registry."""
        agent = agent_loop_instance
        # 工具注册通过 patch 模拟，验证调用发生
        # 实际验证在 test_collaboration.py 中
        assert agent.tools is not None