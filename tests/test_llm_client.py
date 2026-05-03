"""
Tests for src/llm_client.py

Coverage targets:
- LLMClient initialization
- reason() method
- stream_reason() method
- get_context_window()
- get_model_info()
- get_active_provider()
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from llm_client import LLMClient
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
        self.stream_chat_completion = self._mock_stream()
        self._model_config = MockModelConfig()

    def _mock_stream(self):
        """Mock stream generator"""
        async def generator(*args, **kwargs):
            yield {'choices': [{'delta': {'content': 'chunk1'}}]}
            yield {'choices': [{'delta': {'content': 'chunk2'}}]}
            yield {'choices': [{'delta': {'content': ''}}]}
        return generator

    def get_model_config(self, model_id):
        return self._model_config

    async def get_active_provider(self):
        return "test_provider"


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


class TestLLMClientStreamReason:
    """Test LLMClient.stream_reason() method"""

    @pytest.mark.asyncio
    async def test_stream_reason_basic(self):
        """Test basic stream reason call"""
        gateway = MockGateway()
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