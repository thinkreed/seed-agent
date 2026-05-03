"""
Tests for src/llm_client.py - 三件套大脑

Coverage targets:
- LLMClient initialization
- reason() method
- stream_reason() method
- get_context_window()
- get_model_info()
- get_active_provider()
- get_rate_limit_status()
- LLMClientPool
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm_client import LLMClient, LLMClientPool, ReasonResult
from request_queue import RequestPriority


class MockModelConfig:
    """Mock model config for testing"""
    def __init__(self):
        self.contextWindow = 128000
        self.maxOutputTokens = 4096


class MockGateway:
    """Mock LLM Gateway for testing"""
    def __init__(self):
        self.chat_completion = AsyncMock(return_value={
            'choices': [{'message': {'content': 'test response'}}],
            'usage': {'total_tokens': 100},
            'model': 'test-model'
        })
        self._model_config = MockModelConfig()

    def _mock_stream(self):
        """Mock stream generator"""
        async def generator(*args, **kwargs):
            yield {'choices': [{'delta': {'content': 'chunk1'}}]}
            yield {'choices': [{'delta': {'content': 'chunk2'}}]}
            yield {'choices': [{'delta': {'content': ''}}]}

        self.stream_chat_completion = generator
        return generator

    def get_model_config(self, model_id):
        return self._model_config

    async def get_active_provider(self):
        return "test_provider"

    def get_rate_limit_status(self):
        status = MagicMock()
        status.tokens_available = 100
        status.window_usage_ratio = 0.5
        return status

    def is_rate_limited(self):
        return False


class TestLLMClientInit:
    """Test LLMClient initialization"""

    def test_init_default_values(self):
        """Test initialization with default values"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-provider/test-model")

        assert client.gateway == gateway
        assert client.model_id == "test-provider/test-model"
        assert client.default_priority == RequestPriority.NORMAL

    def test_init_custom_priority(self):
        """Test initialization with custom priority"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model", default_priority=RequestPriority.CRITICAL)

        assert client.default_priority == RequestPriority.CRITICAL

    def test_model_config_cached(self):
        """Test model config is cached on init"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        assert client._model_config is not None
        assert client._model_config.contextWindow == 128000


class TestLLMClientReason:
    """Test LLMClient.reason() method"""

    @pytest.mark.asyncio
    async def test_reason_basic(self):
        """Test basic reason call"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        response = await client.reason(context)

        assert response['choices'][0]['message']['content'] == 'test response'
        gateway.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_reason_with_tools(self):
        """Test reason call with tools"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        response = await client.reason(context, tools=tools)

        gateway.chat_completion.assert_called_with(
            "test-model",
            context,
            priority=RequestPriority.NORMAL,
            tools=tools
        )

    @pytest.mark.asyncio
    async def test_reason_with_priority(self):
        """Test reason call with custom priority"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        response = await client.reason(context, priority=RequestPriority.CRITICAL)

        gateway.chat_completion.assert_called_with(
            "test-model",
            context,
            priority=RequestPriority.CRITICAL,
            tools=None
        )

    @pytest.mark.asyncio
    async def test_reason_with_kwargs(self):
        """Test reason call with extra kwargs"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        response = await client.reason(context, temperature=0.5, max_tokens=100)

        # Verify kwargs were passed
        call_kwargs = gateway.chat_completion.call_args.kwargs
        assert 'temperature' in call_kwargs or call_kwargs.get('temperature') == 0.5

    @pytest.mark.asyncio
    async def test_reason_exception_handling(self):
        """Test reason exception handling"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(side_effect=Exception("API error"))
        client = LLMClient(gateway, "test-model")

        with pytest.raises(Exception) as exc_info:
            await client.reason([{"role": "user", "content": "hello"}])

        assert "API error" in str(exc_info.value)


class TestLLMClientStreamReason:
    """Test LLMClient.stream_reason() method"""

    @pytest.mark.asyncio
    async def test_stream_reason_basic(self):
        """Test basic stream reason call"""
        gateway = MockGateway()
        gateway._mock_stream()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        chunks = []
        async for chunk in client.stream_reason(context):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0]['choices'][0]['delta']['content'] == 'chunk1'

    @pytest.mark.asyncio
    async def test_stream_reason_with_tools(self):
        """Test stream reason with tools"""
        gateway = MockGateway()
        gateway._mock_stream()
        client = LLMClient(gateway, "test-model")

        context = [{"role": "user", "content": "hello"}]
        tools = [{"type": "function", "function": {"name": "test"}}]

        chunks = []
        async for chunk in client.stream_reason(context, tools=tools):
            chunks.append(chunk)

        assert len(chunks) > 0


class TestLLMClientHelpers:
    """Test LLMClient helper methods"""

    def test_get_context_window(self):
        """Test get_context_window"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        window = client.get_context_window()
        assert window == 128000

    def test_get_max_output_tokens(self):
        """Test get_max_output_tokens"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        max_tokens = client.get_max_output_tokens()
        assert max_tokens == 4096

    def test_get_model_info(self):
        """Test get_model_info"""
        gateway = MockGateway()
        client = LLMClient(gateway, "provider/model-id")

        info = client.get_model_info()

        assert info['model_id'] == "provider/model-id"
        assert info['context_window'] == 128000
        assert info['max_output_tokens'] == 4096
        assert info['provider'] == "provider"

    def test_get_model_info_no_provider(self):
        """Test get_model_info when model_id has no provider prefix"""
        gateway = MockGateway()
        client = LLMClient(gateway, "model-only")

        info = client.get_model_info()
        assert info['provider'] == "unknown"

    @pytest.mark.asyncio
    async def test_get_active_provider(self):
        """Test get_active_provider"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        provider = await client.get_active_provider()
        assert provider == "test_provider"

    def test_get_rate_limit_status(self):
        """Test get_rate_limit_status"""
        gateway = MockGateway()
        client = LLMClient(gateway, "test-model")

        status = client.get_rate_limit_status()

        assert status is not None
        assert status['tokens_available'] == 100
        assert status['window_usage_ratio'] == 0.5
        assert status['is_limited'] is False

    def test_get_rate_limit_status_none(self):
        """Test get_rate_limit_status when gateway returns None"""
        gateway = MockGateway()
        gateway.get_rate_limit_status = MagicMock(return_value=None)
        client = LLMClient(gateway, "test-model")

        status = client.get_rate_limit_status()
        assert status is None


class TestReasonResult:
    """Test ReasonResult class"""

    def test_reason_result_init(self):
        """Test ReasonResult initialization"""
        result = ReasonResult(
            response={'choices': [{'message': {'content': 'test'}}]},
            model_id='test-model',
            duration_ms=100.0,
            tokens_used=50
        )

        assert result.model_id == 'test-model'
        assert result.duration_ms == 100.0
        assert result.tokens_used == 50

    def test_get_content(self):
        """Test ReasonResult.get_content"""
        result = ReasonResult(
            response={'choices': [{'message': {'content': 'test content'}}]},
            model_id='test-model',
            duration_ms=100.0
        )

        content = result.get_content()
        assert content == 'test content'

    def test_get_tool_calls(self):
        """Test ReasonResult.get_tool_calls"""
        result = ReasonResult(
            response={'choices': [{'message': {
                'content': None,
                'tool_calls': [{'id': 'call_1'}]
            }}]},
            model_id='test-model',
            duration_ms=100.0
        )

        tool_calls = result.get_tool_calls()
        assert len(tool_calls) == 1

    def test_is_tool_call(self):
        """Test ReasonResult.is_tool_call"""
        result_with_tools = ReasonResult(
            response={'choices': [{'message': {'tool_calls': [{'id': 'call_1'}]}}]},
            model_id='test-model',
            duration_ms=100.0
        )

        result_without_tools = ReasonResult(
            response={'choices': [{'message': {'content': 'text'}}]},
            model_id='test-model',
            duration_ms=100.0
        )

        assert result_with_tools.is_tool_call() is True
        assert result_without_tools.is_tool_call() is False

    def test_to_dict(self):
        """Test ReasonResult.to_dict"""
        result = ReasonResult(
            response={'choices': [{'message': {'content': 'test'}}]},
            model_id='test-model',
            duration_ms=100.0
        )

        d = result.to_dict()
        assert d['choices'][0]['message']['content'] == 'test'


class TestLLMClientPool:
    """Test LLMClientPool"""

    def test_init(self):
        """Test LLMClientPool initialization"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)

        assert pool._gateway == gateway
        assert len(pool._clients) == 0

    def test_add_client(self):
        """Test adding client to pool"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)

        client = pool.add_client("test-model", is_primary=True)

        assert len(pool._clients) == 1
        assert pool._primary_model == "test-model"
        assert client.model_id == "test-model"

    def test_get_client(self):
        """Test getting client from pool"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("model1", is_primary=True)
        pool.add_client("model2")

        client1 = pool.get_client("model1")
        client_default = pool.get_client()

        assert client1.model_id == "model1"
        assert client_default.model_id == "model1"

    def test_get_client_not_found(self):
        """Test getting client not in pool"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)

        with pytest.raises(ValueError):
            pool.get_client("nonexistent")

    def test_get_primary_client(self):
        """Test getting primary client"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("primary", is_primary=True)

        client = pool.get_primary_client()

        assert client.model_id == "primary"

    def test_get_primary_client_no_primary(self):
        """Test getting primary client when none set"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)

        with pytest.raises(ValueError):
            pool.get_primary_client()

    def test_list_models(self):
        """Test listing models"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("model1")
        pool.add_client("model2")

        models = pool.list_models()

        assert len(models) == 2
        assert "model1" in models

    def test_remove_client(self):
        """Test removing client"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("model1", is_primary=True)
        pool.add_client("model2")

        result = pool.remove_client("model1")

        assert result is True
        assert "model1" not in pool._clients
        assert pool._primary_model == "model2"

    def test_remove_client_not_found(self):
        """Test removing client not in pool"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)

        result = pool.remove_client("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_reason_with_fallback(self):
        """Test reason with fallback"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("primary", is_primary=True)
        pool.add_client("fallback1")

        response = await pool.reason_with_fallback(
            [{"role": "user", "content": "hello"}],
            fallback_models=["fallback1"]
        )

        assert response['choices'][0]['message']['content'] == 'test response'

    @pytest.mark.asyncio
    async def test_reason_with_fallback_all_fail(self):
        """Test reason with fallback when all fail"""
        gateway = MockGateway()
        gateway.chat_completion = AsyncMock(side_effect=Exception("API error"))
        pool = LLMClientPool(gateway)
        pool.add_client("primary", is_primary=True)
        pool.add_client("fallback1")

        with pytest.raises(RuntimeError) as exc_info:
            await pool.reason_with_fallback(
                [{"role": "user", "content": "hello"}],
                fallback_models=["fallback1"]
            )

        assert "All models failed" in str(exc_info.value)

    def test_get_pool_status(self):
        """Test getting pool status"""
        gateway = MockGateway()
        pool = LLMClientPool(gateway)
        pool.add_client("model1", is_primary=True)
        pool.add_client("model2")

        status = pool.get_pool_status()

        assert status["primary_model"] == "model1"
        assert status["clients_count"] == 2
        assert len(status["models"]) == 2