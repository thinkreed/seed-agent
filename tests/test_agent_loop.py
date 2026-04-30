"""
Tests for src/agent_loop.py

Coverage targets:
- AgentLoop initialization and configuration
- Context window management (_get_model_context_window, _estimate_context_size)
- Token caching (_cache_message_tokens, _message_token_cache)
- Message building (_build_messages)
- History summarization (_summarize_history, _maybe_summarize)
- Tool call execution (_execute_tool_calls, path conflict detection)
- Tool delta processing (_process_tool_delta)
- Skill outcome tracking (_evaluate_and_record_skill_outcomes)
- Session management (clear_history, interrupt)
- MaxIterationsExceeded exception
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Note: Only use @pytest.mark.asyncio on actual async test functions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent_loop import AgentLoop, MaxIterationsExceeded, ProviderNotFoundError, ToolNotFoundError


# ==================== Fixtures ====================

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
    gateway.chat_completion = AsyncMock(return_value={
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': 'Hello, I am the assistant.'
            }
        }]
    })
    gateway.stream_chat_completion = AsyncMock()
    return gateway


@pytest.fixture
def mock_gateway_with_model():
    """Mock LLMGateway with model context window config."""
    gateway = MagicMock()
    gateway.config = MagicMock()
    gateway.config.agents = MagicMock()
    gateway.config.agents['defaults'] = MagicMock()
    gateway.config.agents['defaults'].defaults = MagicMock()
    gateway.config.agents['defaults'].defaults.primary = "openai/gpt-4o"
    
    # Model config with context window
    mock_model = MagicMock()
    mock_model.id = "gpt-4o"
    mock_model.contextWindow = 128000
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
    return gateway


# ==================== Common Patch Helper ====================

def agent_patches(session_id='test_session'):
    """Common patches for AgentLoop initialization."""
    return patch.multiple(
        'agent_loop',
        ToolRegistry=MagicMock,
        SkillLoader=MagicMock,
        SubagentManager=MagicMock,
    )

def full_agent_patches(session_id='test_session'):
    """Full set of patches for AgentLoop initialization."""
    # Use simple no-op functions instead of MagicMock for register functions
    def noop(*args, **kwargs):
        pass
    
    def mock_init(*args, **kwargs):
        pass
    
    # Create a mock SkillLoader that returns a real string for get_skills_prompt
    mock_skill_loader = MagicMock()
    mock_skill_loader.return_value.get_skills_prompt.return_value = "\n## Available Skills\n- test-skill"
    
    return [
        patch('agent_loop.ToolRegistry', return_value=MagicMock()),
        patch('agent_loop.SkillLoader', mock_skill_loader),
        patch('scheduler.TaskScheduler', return_value=MagicMock()),
        patch('agent_loop.SubagentManager', return_value=MagicMock()),
        patch('tools.subagent_tools.init_subagent_manager', mock_init),
        patch('tools.builtin_tools.register_builtin_tools', noop),
        patch('tools.memory_tools.register_memory_tools', noop),
        patch('tools.skill_loader.register_skill_tools', noop),
        patch('scheduler.register_scheduler_tools', noop),
        patch('tools.ralph_tools.register_ralph_tools', noop),
        patch('tools.subagent_tools.register_subagent_tools', noop),
        # Patch in the agent_loop module namespace (where it's imported to)
        patch('agent_loop._generate_session_filename', return_value=session_id),
        patch('tiktoken.encoding_for_model', side_effect=KeyError),
        patch('tiktoken.get_encoding', return_value=MagicMock()),
    ]

class _PatchManager:
    """Context manager for multiple patches."""
    def __init__(self, patches):
        self._patches = patches
        self._entered = []
    
    def __enter__(self):
        for p in self._patches:
            self._entered.append(p.__enter__())
        return self
    
    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.__exit__(*args)

def create_agent(gateway, model_id="openai/gpt-4o", session_id='test_session', **kwargs):
    """Helper to create AgentLoop with all patches applied."""
    patches = full_agent_patches(session_id)
    mgr = _PatchManager(patches)
    mgr.__enter__()
    try:
        agent = AgentLoop(gateway=gateway, model_id=model_id, **kwargs)
        return agent, mgr
    except:
        mgr.__exit__(None, None, None)
        raise


# ==================== Fixtures ====================

@pytest.fixture
def agent_loop_instance(mock_gateway):
    """Create an AgentLoop instance with mocked dependencies."""
    agent, mgr = create_agent(mock_gateway, session_id='test_session_123')
    # Store manager for cleanup
    agent._patch_manager = mgr
    yield agent
    mgr.__exit__(None, None, None)


# ==================== Exception Tests ====================

class TestExceptions:
    """Test custom exceptions."""
    
    def test_max_iterations_exceeded(self):
        """Test MaxIterationsExceeded exception."""
        exc = MaxIterationsExceeded("Test message")
        assert str(exc) == "Test message"
    
    def test_provider_not_found_error(self):
        """Test ProviderNotFoundError."""
        exc = ProviderNotFoundError("Test message")
        assert str(exc) == "Test message"
    
    def test_tool_not_found_error(self):
        """Test ToolNotFoundError."""
        exc = ToolNotFoundError("Test message")
        assert str(exc) == "Test message"


# ==================== Initialization Tests ====================

class TestAgentLoopInit:
    """Test AgentLoop initialization."""
    
    def test_init_default_values(self, agent_loop_instance, mock_gateway):
        """Test initialization with default values."""
        agent = agent_loop_instance
        assert agent.gateway == mock_gateway
        assert agent.model_id == "openai/gpt-4o"
        assert agent.max_iterations == 30
        assert agent.summary_interval == 10
        assert agent.history == []
        assert agent._conversation_rounds == 0
        assert agent._last_summary is None
        assert agent.session_id == 'test_session_123'
        assert agent._pending_skill_outcomes == []
        assert agent.context_usage_threshold == 0.75
        assert agent._message_token_cache == []
        assert agent._system_prompt_tokens == 0
        assert agent._pending_user_input is None
    
    def test_init_custom_values(self, mock_gateway):
        """Test initialization with custom values."""
        agent, mgr = create_agent(
            mock_gateway,
            model_id="anthropic/claude-3",
            system_prompt="You are a test agent",
            max_iterations=50,
            summary_interval=5,
            session_id="my_session"
        )
        try:
            assert agent.model_id == "anthropic/claude-3"
            assert agent.max_iterations == 50
            assert agent.summary_interval == 5
            assert agent.session_id == "my_session"
            # system_prompt is concatenated with skills_prompt (mocked), so check str representation
            assert "You are a test agent" in str(agent.system_prompt)
        finally:
            mgr.__exit__(None, None, None)
    
    def test_init_generates_session_id(self, mock_gateway):
        """Test session ID generation when not provided."""
        agent, mgr = create_agent(mock_gateway, session_id='auto_gen_session')
        try:
            assert agent.session_id == 'auto_gen_session'
        finally:
            mgr.__exit__(None, None, None)


# ==================== Context Window Tests ====================

class TestContextWindow:
    """Test context window management."""
    
    def test_get_model_context_window(self, agent_loop_instance):
        """Test context window retrieval."""
        agent = agent_loop_instance
        agent.gateway.config.models = {}
        # Should return default when model not found
        result = agent._get_model_context_window()
        assert result == 100000  # Default fallback
    
    def test_get_model_context_window_with_config(self, mock_gateway_with_model):
        """Test context window retrieval with model config."""
        agent, mgr = create_agent(mock_gateway_with_model, model_id="openai/gpt-4o")
        try:
            result = agent._get_model_context_window()
            assert result == 128000
        finally:
            mgr.__exit__(None, None, None)
    
    def test_get_model_context_window_fallback(self, mock_gateway_with_model):
        """Test context window fallback for unknown model."""
        agent, mgr = create_agent(mock_gateway_with_model, model_id="unknown/model-x")
        try:
            result = agent._get_model_context_window()
            assert result == 100000  # Default fallback
        finally:
            mgr.__exit__(None, None, None)


# ==================== Token Encoding Tests ====================

class TestTokenEncoding:
    """Test token encoding and caching."""
    
    def test_encode_text_with_encoding(self, agent_loop_instance):
        """Test text encoding with tokenizer."""
        agent = agent_loop_instance
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]
        agent._encoding = mock_encoding
        
        result = agent._encode_text("Hello world")
        assert result == 5
        mock_encoding.encode.assert_called_once_with("Hello world")
    
    def test_encode_text_fallback(self, agent_loop_instance):
        """Test fallback encoding when no tokenizer."""
        agent = agent_loop_instance
        agent._encoding = None
        
        result = agent._encode_text("Hello world")
        # Fallback: len(text) * 0.7 = 11 * 0.7 = 7.7 -> 7
        assert result == 7
    
    def test_cache_message_tokens_string(self, agent_loop_instance):
        """Test caching tokens for string content message."""
        agent = agent_loop_instance
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2, 3]
        
        msg = {"role": "user", "content": "Hello"}
        result = agent._cache_message_tokens(msg)
        assert result == 3
    
    def test_cache_message_tokens_list(self, agent_loop_instance):
        """Test caching tokens for list content message."""
        agent = agent_loop_instance
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2]
        
        msg = {"role": "user", "content": [{"text": "Hello"}, {"text": "World"}]}
        result = agent._cache_message_tokens(msg)
        assert result == 4  # 2 + 2
    
    def test_cache_message_tokens_with_tool_calls(self, agent_loop_instance):
        """Test caching tokens for message with tool calls."""
        agent = agent_loop_instance
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2, 3]
        
        msg = {
            "role": "assistant",
            "content": "Using tool",
            "tool_calls": [{"id": "1", "function": {"name": "test", "arguments": "{}"}}]
        }
        result = agent._cache_message_tokens(msg)
        # Content tokens + tool_calls tokens
        assert result >= 3


# ==================== Context Size Estimation Tests ====================

class TestContextSizeEstimation:
    """Test context size estimation."""
    
    def test_estimate_context_size_empty(self, agent_loop_instance):
        """Test estimation with empty history."""
        agent = agent_loop_instance
        agent.system_prompt = "System prompt"
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2, 3, 4, 5]
        
        result = agent._estimate_context_size()
        assert result == 5  # system prompt tokens
    
    def test_estimate_context_size_with_history(self, agent_loop_instance):
        """Test estimation with message history."""
        agent = agent_loop_instance
        agent.system_prompt = "System"
        agent.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2, 3]
        
        result = agent._estimate_context_size()
        # system (3) + msg1 (3) + msg2 (3) = 9
        assert result == 9
    
    def test_estimate_context_size_incremental(self, agent_loop_instance):
        """Test incremental cache update."""
        agent = agent_loop_instance
        agent.system_prompt = "System"
        agent.history = [{"role": "user", "content": "First"}]
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2]
        
        # First call
        agent._estimate_context_size()
        assert len(agent._message_token_cache) == 1
        
        # Add another message
        agent.history.append({"role": "assistant", "content": "Second"})
        agent._estimate_context_size()
        assert len(agent._message_token_cache) == 2
        # Only new message should be encoded
    
    def test_estimate_context_size_after_truncation(self, agent_loop_instance):
        """Test cache rebuild after history truncation."""
        agent = agent_loop_instance
        agent.system_prompt = "System"
        agent.history = [
            {"role": "user", "content": "Msg1"},
            {"role": "assistant", "content": "Msg2"},
            {"role": "user", "content": "Msg3"}
        ]
        agent._encoding = MagicMock()
        agent._encoding.encode.return_value = [1, 2]
        
        # Build cache
        agent._estimate_context_size()
        assert len(agent._message_token_cache) == 3
        
        # Truncate history (simulate summarization)
        agent.history = agent.history[-1:]
        agent._estimate_context_size()
        assert len(agent._message_token_cache) == 1
        assert agent._system_prompt_tokens > 0


# ==================== Message Building Tests ====================

class TestMessageBuilding:
    """Test message building."""
    
    def test_build_messages_with_system(self, agent_loop_instance):
        """Test building messages with system prompt."""
        agent = agent_loop_instance
        agent.system_prompt = "You are helpful"
        agent.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        
        messages = agent._build_messages()
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "You are helpful"}
        assert messages[1] == {"role": "user", "content": "Hello"}
        assert messages[2] == {"role": "assistant", "content": "Hi"}
    
    def test_build_messages_without_system(self, agent_loop_instance):
        """Test building messages without system prompt."""
        agent = agent_loop_instance
        agent.system_prompt = None
        agent.history = [{"role": "user", "content": "Test"}]
        
        messages = agent._build_messages()
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "Test"}
    
    def test_build_messages_empty_history(self, agent_loop_instance):
        """Test building messages with empty history."""
        agent = agent_loop_instance
        agent.system_prompt = "System"
        agent.history = []
        
        messages = agent._build_messages()
        assert len(messages) == 1
        assert messages[0] == {"role": "system", "content": "System"}


# ==================== Tool Delta Processing Tests ====================

class TestToolDeltaProcessing:
    """Test tool call delta processing."""
    
    def test_process_tool_delta_first_chunk(self, agent_loop_instance):
        """Test processing first delta chunk."""
        agent = agent_loop_instance
        accumulator = {}
        
        delta = {
            'index': 0,
            'id': 'call_123',
            'type': 'function',
            'function': {'name': 'file_read', 'arguments': '{"path":'}
        }
        
        agent._process_tool_delta([delta], accumulator)
        
        assert 0 in accumulator
        assert accumulator[0]['id'] == 'call_123'
        assert accumulator[0]['function']['name'] == 'file_read'
        assert accumulator[0]['function']['arguments'] == '{"path":'
    
    def test_process_tool_delta_incremental(self, agent_loop_instance):
        """Test incremental delta processing."""
        agent = agent_loop_instance
        accumulator = {
            0: {
                'id': 'call_123',
                'type': 'function',
                'function': {'name': 'file_read', 'arguments': '{"path":'}
            }
        }
        
        delta = {
            'index': 0,
            'function': {'arguments': '"test.txt"}'}
        }
        
        agent._process_tool_delta([delta], accumulator)
        
        assert accumulator[0]['function']['arguments'] == '{"path":"test.txt"}'
    
    def test_process_tool_delta_multiple_calls(self, agent_loop_instance):
        """Test processing multiple tool calls."""
        agent = agent_loop_instance
        accumulator = {}
        
        deltas = [
            {'index': 0, 'id': 'call_1', 'function': {'name': 'tool_a', 'arguments': '{}'}},
            {'index': 1, 'id': 'call_2', 'function': {'name': 'tool_b', 'arguments': '{}'}}
        ]
        
        agent._process_tool_delta(deltas, accumulator)
        
        assert 0 in accumulator
        assert 1 in accumulator
        assert accumulator[0]['function']['name'] == 'tool_a'
        assert accumulator[1]['function']['name'] == 'tool_b'


# ==================== Tool Execution Tests ====================

class TestToolExecution:
    """Test tool call execution."""
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_success(self, agent_loop_instance):
        """Test successful tool execution."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.execute = AsyncMock(return_value="File content")
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'file_read',
                    'arguments': '{"path": "test.txt"}'
                }
            }
        ]
        
        results = await agent._execute_tool_calls(tool_calls)
        
        assert len(results) == 1
        assert results[0]['role'] == 'tool'
        assert results[0]['tool_call_id'] == 'call_1'
        assert results[0]['content'] == 'File content'
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_json_parse_error(self, agent_loop_instance):
        """Test tool execution with invalid JSON arguments."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.execute = AsyncMock(return_value="Result")
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'file_read',
                    'arguments': 'invalid json{{{'''
                }
            }
        ]
        
        results = await agent._execute_tool_calls(tool_calls)
        
        # Should use empty dict and still execute
        agent.tools.execute.assert_called_once()
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_exception(self, agent_loop_instance):
        """Test tool execution with exception."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.execute = AsyncMock(side_effect=Exception("Tool error"))
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'file_read',
                    'arguments': '{}'
                }
            }
        ]
        
        results = await agent._execute_tool_calls(tool_calls)
        
        assert len(results) == 1
        assert 'Error: Tool error' in results[0]['content']
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_path_conflict(self, agent_loop_instance):
        """Test concurrent write conflict detection."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'file_write',
                    'arguments': '{"path": "test.txt", "content": "a"}'
                }
            },
            {
                'id': 'call_2',
                'function': {
                    'name': 'file_edit',
                    'arguments': '{"path": "test.txt", "old_str": "a", "new_str": "b"}'
                }
            }
        ]
        
        results = await agent._execute_tool_calls(tool_calls)
        
        # Should detect conflict and return error for all calls
        assert len(results) == 2
        assert 'Concurrent write conflict' in results[0]['content']
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_skill_tracking(self, agent_loop_instance):
        """Test skill outcome tracking during tool execution."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.execute = AsyncMock(return_value="Skill loaded successfully")
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'load_skill',
                    'arguments': '{"name": "test-skill"}'
                }
            }
        ]
        
        await agent._execute_tool_calls(tool_calls)
        
        assert len(agent._pending_skill_outcomes) == 1
        assert agent._pending_skill_outcomes[0]['skill_name'] == 'test-skill'
    
    @pytest.mark.asyncio
    async def test_execute_tool_calls_empty_args(self, agent_loop_instance):
        """Test tool execution with empty arguments."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.execute = AsyncMock(return_value="Result")
        
        tool_calls = [
            {
                'id': 'call_1',
                'function': {
                    'name': 'list_skills',
                    'arguments': ''
                }
            }
        ]
        
        results = await agent._execute_tool_calls(tool_calls)
        
        assert len(results) == 1
        agent.tools.execute.assert_called_once_with('list_skills')


# ==================== Signal Extraction Tests ====================

class TestSignalExtraction:
    """Test signal extraction from context."""
    
    def test_extract_signals_from_context(self, agent_loop_instance):
        """Test signal extraction from recent messages."""
        agent = agent_loop_instance
        agent.history = [
            {"role": "user", "content": "Please help me with file operations"},
            {"role": "assistant", "content": "I will use file_read tool"},
            {"role": "user", "content": "Also check the diagnosis system"}
        ]
        
        signals = agent._extract_signals_from_context()
        
        assert isinstance(signals, list)
        assert len(signals) <= 10
        # Should contain words from recent messages (first 5 words of each)
        # The last message starts with "Also check the diagnosis system"
        assert len(signals) > 0
        # Check that signals contain words from the messages
        all_signals_text = ' '.join(signals).lower()
        assert any(word in all_signals_text for word in ['please', 'also', 'check', 'diagnosis'])
    
    def test_extract_signals_empty_history(self, agent_loop_instance):
        """Test signal extraction with empty history."""
        agent = agent_loop_instance
        agent.history = []
        
        signals = agent._extract_signals_from_context()
        
        assert signals == []


# ==================== Skill Outcome Evaluation Tests ====================

class TestSkillOutcomeEvaluation:
    """Test skill outcome evaluation and recording."""
    
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
    
    @patch('agent_loop._record_skill_outcome')
    def test_evaluate_skill_outcome_partial(self, mock_record, agent_loop_instance):
        """Test partial skill outcome (security warning)."""
        agent = agent_loop_instance
        agent._pending_skill_outcomes = [
            {
                'skill_name': 'risky-skill',
                'result': 'Security Warning: something risky',
                'signals': ['test'],
                'failed': False
            }
        ]
        
        agent._evaluate_and_record_skill_outcomes(final_success=True)
        
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs['outcome'] == 'partial'
        assert call_kwargs['score'] == 0.5
    
    @patch('agent_loop._record_skill_outcome')
    def test_evaluate_skill_outcome_final_failure(self, mock_record, agent_loop_instance):
        """Test skill outcome with final_success=False."""
        agent = agent_loop_instance
        agent._pending_skill_outcomes = [
            {
                'skill_name': 'test-skill',
                'result': 'OK',
                'signals': [],
                'failed': False
            }
        ]
        
        agent._evaluate_and_record_skill_outcomes(final_success=False)
        
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs['score'] == 0.8
    
    @patch('agent_loop._record_skill_outcome')
    def test_evaluate_skill_outcome_record_error(self, mock_record, agent_loop_instance):
        """Test handling of record_skill_outcome exception."""
        agent = agent_loop_instance
        agent._pending_skill_outcomes = [
            {
                'skill_name': 'test-skill',
                'result': 'OK',
                'signals': [],
                'failed': False
            }
        ]
        mock_record.side_effect = Exception("DB error")
        
        # Should not raise
        agent._evaluate_and_record_skill_outcomes(final_success=True)
        
        assert len(agent._pending_skill_outcomes) == 0  # Still cleared


# ==================== Session Management Tests ====================

class TestSessionManagement:
    """Test session management."""
    
    @patch('agent_loop._save_session_history')
    @patch('agent_loop._generate_session_filename', return_value='new_session_456')
    def test_clear_history_save(self, mock_gen, mock_save, agent_loop_instance):
        """Test clearing history with save."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Test"}]
        agent._conversation_rounds = 5
        agent._last_summary = "Summary"
        agent._message_token_cache = [1, 2, 3]
        agent._system_prompt_tokens = 10
        
        agent.clear_history(save_current=True)
        
        mock_save.assert_called_once()
        assert agent.history == []
        assert agent._conversation_rounds == 0
        assert agent._last_summary is None
        assert agent._message_token_cache == []
        assert agent._system_prompt_tokens == 0
        assert agent.session_id == 'new_session_456'
    
    def test_clear_history_no_save(self, agent_loop_instance):
        """Test clearing history without save."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Test"}]
        agent._conversation_rounds = 5
        
        with patch('agent_loop._save_session_history') as mock_save:
            agent.clear_history(save_current=False)
            
            mock_save.assert_not_called()
            assert agent.history == []
            assert agent._conversation_rounds == 0
    
    def test_interrupt(self, agent_loop_instance):
        """Test interrupting agent with user input."""
        agent = agent_loop_instance
        
        agent.interrupt("Stop and do this instead")
        
        assert agent._pending_user_input == "Stop and do this instead"


# ==================== Run Loop Tests ====================

class TestRunLoop:
    """Test the main run loop."""
    
    @pytest.mark.asyncio
    async def test_run_single_turn(self, agent_loop_instance):
        """Test single turn execution."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.get_schemas = MagicMock(return_value=[])
        
        response = await agent.run("Hello")
        
        assert agent._conversation_rounds == 1
        assert len(agent.history) == 2  # user + assistant
        assert response == 'Hello, I am the assistant.'
    
    @pytest.mark.asyncio
    async def test_run_max_iterations(self, agent_loop_instance):
        """Test max iterations exceeded."""
        agent = agent_loop_instance
        agent.max_iterations = 2
        agent.tools = MagicMock()
        agent.tools.get_schemas = MagicMock(return_value=[])
        # Always return tool calls to force iterations
        agent.gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [{'id': '1', 'function': {'name': 'test', 'arguments': '{}'}}]
                }
            }]
        })
        agent.tools.execute = AsyncMock(return_value="Done")
        
        with pytest.raises(MaxIterationsExceeded):
            await agent.run("Test")
    
    @pytest.mark.asyncio
    async def test_run_with_pending_input(self, agent_loop_instance):
        """Test run with pending user input (interrupt)."""
        agent = agent_loop_instance
        agent.tools = MagicMock()
        agent.tools.get_schemas = MagicMock(return_value=[])
        
        # Set pending input before run
        agent._pending_user_input = "Interrupt message"
        
        # Run will process the pending input as a new user message
        await agent.run("Initial message")
        
        # Should have processed both messages
        assert agent._conversation_rounds >= 1


# ==================== Summary Tests ====================

class TestSummary:
    """Test history summarization."""
    
    @pytest.mark.asyncio
    async def test_summarize_history_empty(self, agent_loop_instance):
        """Test summarizing empty history."""
        agent = agent_loop_instance
        result = await agent._summarize_history()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_summarize_history_success(self, agent_loop_instance):
        """Test successful history summarization."""
        agent = agent_loop_instance
        agent.history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        agent.gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'content': 'User greeted, assistant responded.'
                }
            }]
        })
        
        result = await agent._summarize_history()
        
        assert result == 'User greeted, assistant responded.'
    
    @pytest.mark.asyncio
    async def test_summarize_history_with_tool_calls(self, agent_loop_instance):
        """Test summarizing history with tool calls."""
        agent = agent_loop_instance
        agent.history = [
            {"role": "user", "content": "Read file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"function": {"name": "file_read"}}]
            },
            {"role": "tool", "content": "File content"}
        ]
        agent.gateway.chat_completion = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'content': 'User requested file read, tool executed.'
                }
            }]
        })
        
        result = await agent._summarize_history()
        
        assert result is not None
        assert 'file_read' in agent.gateway.chat_completion.call_args[0][1][0]['content']
    
    @pytest.mark.asyncio
    async def test_summarize_history_failure(self, agent_loop_instance):
        """Test summarization when LLM call fails."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Hello"}]
        agent.gateway.chat_completion = AsyncMock(side_effect=Exception("API error"))
        
        result = await agent._summarize_history()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_maybe_summarize_no_trigger(self, agent_loop_instance):
        """Test maybe_summarize when no trigger conditions met."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Test"}]
        agent._conversation_rounds = 1
        agent.summary_interval = 10
        agent.context_window = 100000
        agent._estimate_context_size = MagicMock(return_value=1000)  # Well under threshold
        
        # Patch the method directly on the instance
        original_summarize = agent._summarize_history
        agent._summarize_history = AsyncMock()
        
        try:
            await agent._maybe_summarize()
            agent._summarize_history.assert_not_called()
        finally:
            agent._summarize_history = original_summarize
    
    @pytest.mark.asyncio
    async def test_maybe_summarize_round_trigger(self, agent_loop_instance):
        """Test maybe_summarize when round limit reached."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Test"}]
        agent._conversation_rounds = 10
        agent.summary_interval = 10
        agent.context_window = 100000
        agent._estimate_context_size = MagicMock(return_value=1000)
        agent.gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'Summary'}}]
        })
        
        await agent._maybe_summarize()
        
        # Should have summarized and reset rounds
        assert agent._conversation_rounds == 0
        assert agent._last_summary == 'Summary'
    
    @pytest.mark.asyncio
    async def test_maybe_summarize_context_trigger(self, agent_loop_instance):
        """Test maybe_summarize when context window is full."""
        agent = agent_loop_instance
        agent.history = [{"role": "user", "content": "Test"}] * 20
        agent._conversation_rounds = 5
        agent.summary_interval = 10
        agent.context_window = 100000
        # Context > 75% threshold
        agent._estimate_context_size = MagicMock(return_value=80000)
        agent.gateway.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'Context summary'}}]
        })
        
        await agent._maybe_summarize()
        
        # Should have summarized with less history preserved (critical context)
        assert agent._conversation_rounds == 0
        # History should contain summary + preserved messages
        assert any('System Note' in str(msg.get('content', '')) for msg in agent.history)


# ==================== Primary Model Tests ====================

class TestPrimaryModel:
    """Test primary model retrieval."""
    
    def test_get_primary_model(self, agent_loop_instance, mock_gateway):
        """Test getting primary model from config."""
        agent = agent_loop_instance
        result = agent._get_primary_model()
        assert result == "openai/gpt-4o"
