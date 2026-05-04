"""
Tests for src/harness.py - 三件套控制器 + 上下文工程

Coverage targets:
- Harness initialization
- 上下文工程集成
- run_cycle() method
- run_conversation() method
- stream_conversation() method
- _build_context_from_session()
- _route_tool_calls() and _execute_tools_parallel()
- HarnessManager
- Metrics tracking
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from harness import Harness, HarnessManager, MaxIterationsExceeded, MAX_ITERATIONS, CycleResult
from llm_client import LLMClient
from sandbox import Sandbox, IsolationLevel
from session_event_stream import SessionEventStream, EventType
from request_queue import RequestPriority


class MockModelConfig:
    """Mock model config for testing"""
    contextWindow = 128000
    maxOutputTokens = 4096


class MockGateway:
    """Mock LLM Gateway for testing"""
    def __init__(self):
        self._call_count = 0
        self._max_calls_before_done = 1

    def get_model_config(self, model_id):
        return MockModelConfig()

    async def chat_completion(self, model_id, messages, priority=None, tools=None, **kwargs):
        self._call_count += 1

        if self._call_count <= self._max_calls_before_done:
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': f'response {self._call_count}',
                        'tool_calls': [
                            {'id': f'call_{self._call_count}', 'function': {'name': 'test_tool', 'arguments': '{}'}}
                        ]
                    }
                }]
            }
        else:
            return {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': 'final response'
                    }
                }]
            }

    async def stream_chat_completion(self, model_id, messages, priority=None, tools=None, **kwargs):
        yield {'choices': [{'delta': {'content': 'chunk1'}}]}
        yield {'choices': [{'delta': {'content': 'chunk2'}}]}
        yield {'choices': [{'delta': {'content': ''}}]}

    async def get_active_provider(self):
        return "test_provider"

    def get_rate_limit_status(self):
        return None


class MockToolRegistry:
    """Mock ToolRegistry for testing"""
    def __init__(self):
        self._tools = {"test_tool": AsyncMock(return_value="tool result")}

    def get_schemas(self):
        return [{"type": "function", "function": {"name": "test_tool"}}]

    async def execute(self, tool_name, **kwargs):
        return await self._tools[tool_name](**kwargs)


class TestHarnessInit:
    """Test Harness initialization"""

    def test_init_basic(self, tmp_path):
        """Test basic initialization"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        assert harness.llm_client == llm_client
        assert harness.session == session
        assert harness.sandbox == sandbox
        assert harness.max_iterations == MAX_ITERATIONS

    def test_init_custom_iterations(self, tmp_path):
        """Test initialization with custom max_iterations"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, max_iterations=5)

        assert harness.max_iterations == 5

    def test_init_system_prompt(self, tmp_path):
        """Test initialization with system_prompt"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, system_prompt="test prompt")

        assert harness.system_prompt == "test prompt"

    def test_init_metrics_empty(self, tmp_path):
        """Test metrics initialized empty"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        assert len(harness._metrics) == 0

    def test_init_context_window(self, tmp_path):
        """Test initialization with context_window"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, context_window=50000)

        assert harness._context_window == 50000

    def test_init_enable_pruning(self, tmp_path):
        """Test initialization with enable_pruning"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, enable_pruning=False)

        assert harness._enable_pruning is False


class TestHarnessContextEngineering:
    """Test Harness 上下文工程集成"""

    def test_build_context_without_context_engineering(self, tmp_path):
        """Test _build_context_from_session without ContextEngineering."""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        session.emit_event(EventType.USER_INPUT, {"content": "hello"})
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        context = harness._build_context_from_session()

        assert isinstance(context, list)
        assert len(context) > 0

    def test_build_context_with_system_prompt(self, tmp_path):
        """Test _build_context_from_session with system prompt."""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(
            llm_client, session, sandbox,
            system_prompt="You are helpful"
        )

        context = harness._build_context_from_session()

        assert len(context) > 0
        assert context[0]["role"] == "system"

    def test_set_current_task(self, tmp_path):
        """Test set_current_task method."""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        harness.set_current_task("重构 agent_loop.py")

        assert harness._current_task == "重构 agent_loop.py"


class TestHarnessRunCycle:
    """Test Harness.run_cycle()"""

    @pytest.mark.asyncio
    async def test_run_cycle_with_tool_calls(self, tmp_path):
        """Test run_cycle with tool calls"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [{'id': 'call_1', 'function': {'name': 'test_tool', 'arguments': '{}'}}]
                }
            }]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, max_iterations=2)

        result = await harness.run_cycle()

        assert result["continue_loop"] is True
        assert result["tool_results"] is not None
        assert len(result["tool_results"]) == 1

    @pytest.mark.asyncio
    async def test_run_cycle_without_tool_calls(self, tmp_path):
        """Test run_cycle without tool calls (completion)"""
        gateway = MockGateway()
        gateway._max_calls_before_done = 0
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'done'}}]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        result = await harness.run_cycle()

        assert result["continue_loop"] is False
        assert result["tool_results"] is None

    @pytest.mark.asyncio
    async def test_run_cycle_events_recorded(self, tmp_path):
        """Test run_cycle records events"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'response'}}]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        await harness.run_cycle()

        events = session.get_events()
        llm_events = [e for e in events if e["type"] == EventType.LLM_RESPONSE.value]
        assert len(llm_events) == 1


class TestHarnessRunConversation:
    """Test Harness.run_conversation()"""

    @pytest.mark.asyncio
    async def test_run_conversation_basic(self, tmp_path):
        """Test basic conversation"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'final answer'}}]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        result = await harness.run_conversation("hello")

        # run_conversation 返回字典而非字符串
        assert result["content"] == "final answer"
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_conversation_max_iterations(self, tmp_path):
        """Test conversation exceeding max iterations"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'tool_calls': [{'id': 'call_1', 'function': {'name': 'test_tool', 'arguments': '{}'}}]
                }
            }]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, max_iterations=2)

        with pytest.raises(MaxIterationsExceeded) as exc_info:
            await harness.run_conversation("hello")

        assert exc_info.value.iterations == 2

    @pytest.mark.asyncio
    async def test_run_conversation_events_recorded(self, tmp_path):
        """Test events are recorded during conversation"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'done'}}]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        await harness.run_conversation("hello")

        events = session.get_events()
        user_events = [e for e in events if e["type"] == EventType.USER_INPUT.value]
        llm_events = [e for e in events if e["type"] == EventType.LLM_RESPONSE.value]
        end_events = [e for e in events if e["type"] == EventType.SESSION_END.value]

        assert len(user_events) == 1
        assert len(llm_events) >= 1
        assert len(end_events) == 1


class TestHarnessStreamConversation:
    """Test Harness.stream_conversation() - 增强版：支持取消信号、Ask User、钩子"""

    @pytest.mark.asyncio
    async def test_stream_conversation_basic(self, tmp_path):
        """Test basic stream conversation yields real chunks"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        chunks = []
        async for chunk in harness.stream_conversation("hello"):
            chunks.append(chunk)

        assert len(chunks) >= 1
        # Should have chunk and final types
        chunk_types = [c["type"] for c in chunks]
        assert "chunk" in chunk_types or "final" in chunk_types

    @pytest.mark.asyncio
    async def test_stream_conversation_chunk_types(self, tmp_path):
        """Test stream conversation chunk types"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        chunks = []
        async for chunk in harness.stream_conversation("hello"):
            chunks.append(chunk)

        # 验证 chunk 类型
        assert chunks[-1]["type"] == "final"

    @pytest.mark.asyncio
    async def test_stream_conversation_with_signal(self, tmp_path):
        """Test stream conversation with abort signal"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        # Create abort signal
        from abort_signal import AbortController
        controller = AbortController()
        signal = controller.signal

        # Start streaming
        chunks = []
        async for chunk in harness.stream_conversation("hello", signal=signal):
            chunks.append(chunk)
            # Abort after first chunk
            if len(chunks) == 1:
                controller.abort(reason="test_cancel")

        # Should have received at least one chunk before abort
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_stream_conversation_events_recorded(self, tmp_path):
        """Test events are recorded during stream conversation"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        async for chunk in harness.stream_conversation("hello"):
            pass  # consume all chunks

        events = session.get_events()
        user_events = [e for e in events if e["type"] == EventType.USER_INPUT.value]
        llm_events = [e for e in events if e["type"] == EventType.LLM_RESPONSE.value]

        assert len(user_events) == 1
        assert len(llm_events) >= 1

    @pytest.mark.asyncio
    async def test_stream_resume_with_user_response(self, tmp_path):
        """Test stream_resume_with_user_response method"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)
        harness._pending_tool_call_id = "call_123"

        # Create mock response
        from tools.ask_user_types import AskUserResult, UserResponse
        response = AskUserResult(
            request_id="test-123",
            responses=[UserResponse(question_id="0", selected=["Yes"])]
        )

        chunks = []
        async for chunk in harness.stream_resume_with_user_response(response):
            chunks.append(chunk)

        # Should yield chunks and complete
        assert len(chunks) >= 1
        # Verify user response event was recorded
        events = session.get_events()
        response_events = [e for e in events if e["type"] == EventType.USER_RESPONSE.value]
        assert len(response_events) == 1


class TestHarnessToolRouting:
    """Test Harness tool routing"""

    @pytest.mark.asyncio
    async def test_route_tool_calls(self, tmp_path):
        """Test routing tool calls"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        tool_calls = [
            {'id': 'call_1', 'function': {'name': 'test_tool', 'arguments': '{}'}}
        ]

        results = await harness._route_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0]["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_route_tool_calls_events_recorded(self, tmp_path):
        """Test tool call events are recorded"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        tool_calls = [
            {'id': 'call_1', 'function': {'name': 'test_tool', 'arguments': '{}'}}
        ]

        results = await harness._route_tool_calls(tool_calls)

        events = session.get_events()
        tool_call_events = [e for e in events if e["type"] == EventType.TOOL_CALL.value]

        assert len(tool_call_events) == 1


class TestHarnessMetrics:
    """Test Harness metrics tracking"""

    @pytest.mark.asyncio
    async def test_metrics_recorded_after_tool_execution(self, tmp_path):
        """Test metrics recorded after tool execution"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'tool_calls': [{'id': 'call_1', 'function': {'name': 'test_tool', 'arguments': '{}'}}]
                }
            }]
        })
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox, max_iterations=2)
        await harness.run_cycle()

        metrics = harness.get_metrics()
        assert len(metrics) == 1
        assert metrics[0]["tool_name"] == "test_tool"
        assert metrics[0]["success"] is True

    def test_clear_metrics(self, tmp_path):
        """Test clearing metrics"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)
        harness._metrics.append({"tool_name": "test", "duration_ms": 100, "success": True, "error": None})

        harness.clear_metrics()
        assert len(harness._metrics) == 0


class TestHarnessStateRecovery:
    """Test Harness state recovery"""

    def test_replay_to_event(self, tmp_path):
        """Test replaying to event"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        session.emit_event(EventType.USER_INPUT, {"content": "hello"})
        session.emit_event(EventType.LLM_RESPONSE, {"content": "hi"})

        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        state = harness.replay_to_event(1)

        assert isinstance(state, dict)

    def test_get_current_state(self, tmp_path):
        """Test getting current state"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)

        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        state = harness.get_current_state()

        assert isinstance(state, dict)


class TestHarnessHelperMethods:
    """Test Harness helper methods"""

    def test_get_session_id(self, tmp_path):
        """Test getting session ID"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)

        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        assert harness.get_session_id() == "test_session"

    def test_get_event_count(self, tmp_path):
        """Test getting event count"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)
        session.emit_event(EventType.USER_INPUT, {"content": "hello"})

        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        assert harness.get_event_count() >= 1

    def test_get_status(self, tmp_path):
        """Test getting harness status"""
        gateway = MockGateway()
        llm_client = LLMClient(gateway, "test-model")
        session = SessionEventStream("test_session", storage_path=tmp_path)

        sandbox = Sandbox()
        sandbox.register_tools(MockToolRegistry())

        harness = Harness(llm_client, session, sandbox)

        status = harness.get_status()

        assert "session_id" in status
        assert "max_iterations" in status
        assert "llm_model" in status
        assert "metrics_count" in status


class TestHarnessManager:
    """Test HarnessManager"""

    def test_create_harness(self, tmp_path, monkeypatch):
        """Test creating harness through manager"""
        mock_config = MagicMock()
        mock_config.models = {}

        with patch('src.client.LLMGateway') as MockGateway:
            mock_gateway = MagicMock()
            mock_gateway.get_model_config = MagicMock(return_value=MockModelConfig())
            MockGateway.return_value = mock_gateway

            manager = HarnessManager("config_path.yaml")

            assert manager._gateway_config_path == "config_path.yaml"

    def test_list_harnesses(self):
        """Test listing harnesses"""
        manager = HarnessManager("config_path.yaml")
        manager._harnesses = {"h1": MagicMock(), "h2": MagicMock()}

        ids = manager.list_harnesses()
        assert len(ids) == 2
        assert "h1" in ids

    def test_get_harness(self):
        """Test getting harness"""
        manager = HarnessManager("config_path.yaml")
        mock_harness = MagicMock()
        manager._harnesses["test_id"] = mock_harness

        harness = manager.get_harness("test_id")
        assert harness == mock_harness

    def test_get_harness_not_found(self):
        """Test getting harness that doesn't exist"""
        manager = HarnessManager("config_path.yaml")

        harness = manager.get_harness("nonexistent")
        assert harness is None

    def test_destroy_harness(self):
        """Test destroying harness"""
        manager = HarnessManager("config_path.yaml")
        mock_harness = MagicMock()
        mock_sandbox = MagicMock()
        manager._harnesses["test_id"] = mock_harness
        manager._sandboxes["test_id"] = mock_sandbox

        result = manager.destroy_harness("test_id")

        assert result is True
        assert "test_id" not in manager._harnesses
        assert "test_id" not in manager._sandboxes

    def test_destroy_all(self):
        """Test destroying all harnesses"""
        manager = HarnessManager("config_path.yaml")
        manager._harnesses = {"h1": MagicMock(), "h2": MagicMock()}
        manager._sandboxes = {"h1": MagicMock(), "h2": MagicMock()}

        manager.destroy_all()

        assert len(manager._harnesses) == 0
        assert len(manager._sandboxes) == 0

    def test_get_all_status(self):
        """Test getting all status"""
        manager = HarnessManager("config_path.yaml")
        mock_harness1 = MagicMock()
        mock_harness1.get_status = MagicMock(return_value={"id": "h1"})
        mock_harness2 = MagicMock()
        mock_harness2.get_status = MagicMock(return_value={"id": "h2"})
        manager._harnesses = {"h1": mock_harness1, "h2": mock_harness2}

        status = manager.get_all_status()

        assert len(status) == 2
        assert status["h1"]["id"] == "h1"

    def test_get_total_metrics(self):
        """Test getting total metrics"""
        manager = HarnessManager("config_path.yaml")
        mock_harness1 = MagicMock()
        mock_harness1.get_metrics = MagicMock(return_value=[
            {"tool_name": "t1", "duration_ms": 100, "success": True, "error": None}
        ])
        mock_harness2 = MagicMock()
        mock_harness2.get_metrics = MagicMock(return_value=[
            {"tool_name": "t2", "duration_ms": 200, "success": False, "error": "err"}
        ])
        manager._harnesses = {"h1": mock_harness1, "h2": mock_harness2}

        metrics = manager.get_total_metrics()

        assert metrics["total_tool_calls"] == 2
        assert metrics["successful_calls"] == 1
        assert metrics["failed_calls"] == 1
        assert metrics["total_duration_ms"] == 300


class TestMaxIterationsExceeded:
    """Test MaxIterationsExceeded exception"""

    def test_exception_message(self):
        """Test exception message"""
        exc = MaxIterationsExceeded(30)
        assert "30" in str(exc)
        assert exc.iterations == 30


class TestCycleResult:
    """Test CycleResult TypedDict"""

    def test_cycle_result_structure(self):
        """Test CycleResult has expected fields"""
        result: CycleResult = {
            "response": {"choices": []},
            "tool_results": None,
            "continue_loop": False
        }

        assert "response" in result
        assert "tool_results" in result
        assert "continue_loop" in result